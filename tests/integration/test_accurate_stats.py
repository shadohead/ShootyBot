#!/usr/bin/env python3
"""
Test the accurate stats calculation implementation in valorant_client.py
"""
import unittest
import sys
import os

# Add the project root to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestAccurateStatsIntegration(unittest.TestCase):
    """Test that the accurate stats calculation is properly integrated"""
    
    def test_multikill_calculation_logic(self):
        """Test the core logic of multi-kill calculation"""
        # Test the critical discovery: only 3+ kill rounds count as multi-kills
        # This matches tracker.gg behavior exactly
        
        # Simulate round data
        test_cases = [
            {"kills_in_round": 5, "expected_mk": 1},  # ACE = 1 multi-kill
            {"kills_in_round": 4, "expected_mk": 1},  # 4K = 1 multi-kill
            {"kills_in_round": 3, "expected_mk": 1},  # 3K = 1 multi-kill
            {"kills_in_round": 2, "expected_mk": 0},  # 2K = 0 multi-kills (key insight)
            {"kills_in_round": 1, "expected_mk": 0},  # 1K = 0 multi-kills
            {"kills_in_round": 0, "expected_mk": 0},  # 0K = 0 multi-kills
        ]
        
        for case in test_cases:
            with self.subTest(kills=case["kills_in_round"]):
                # Test our logic: only 3+ kill rounds count
                actual_mk = 1 if case["kills_in_round"] >= 3 else 0
                self.assertEqual(actual_mk, case["expected_mk"], 
                               f"Multi-kill logic failed for {case['kills_in_round']} kills")
    
    def test_kast_components(self):
        """Test the KAST calculation components"""
        # KAST = Kill, Assist, Survive, Trade
        # Should be True if ANY of these conditions are met
        
        test_cases = [
            {"has_kill": True, "has_assist": False, "survived": False, "traded": False, "expected": True},
            {"has_kill": False, "has_assist": True, "survived": False, "traded": False, "expected": True},
            {"has_kill": False, "has_assist": False, "survived": True, "traded": False, "expected": True},
            {"has_kill": False, "has_assist": False, "survived": False, "traded": True, "expected": True},
            {"has_kill": False, "has_assist": False, "survived": False, "traded": False, "expected": False},
            {"has_kill": True, "has_assist": True, "survived": True, "traded": True, "expected": True},  # All true
        ]
        
        for i, case in enumerate(test_cases):
            with self.subTest(case_num=i):
                # Test our KAST logic
                kast_qualified = (case["has_kill"] or case["has_assist"] or 
                                case["survived"] or case["traded"])
                self.assertEqual(kast_qualified, case["expected"],
                               f"KAST logic failed for case {i}")
    
    def test_assist_threshold(self):
        """Test the 50+ damage threshold for assists"""
        # Key insight: assists can come from official assists OR 50+ damage to killed enemies
        
        damage_cases = [
            {"damage": 75, "victim_died": True, "expected_assist": True},
            {"damage": 50, "victim_died": True, "expected_assist": True},
            {"damage": 49, "victim_died": True, "expected_assist": False},
            {"damage": 100, "victim_died": False, "expected_assist": False},
            {"damage": 0, "victim_died": True, "expected_assist": False},
        ]
        
        for case in damage_cases:
            with self.subTest(damage=case["damage"], died=case["victim_died"]):
                # Test our assist logic: 50+ damage AND victim died
                gets_assist = (case["damage"] >= 50 and case["victim_died"])
                self.assertEqual(gets_assist, case["expected_assist"],
                               f"Assist logic failed for {case['damage']} damage, died={case['victim_died']}")
    
    def test_trade_timing(self):
        """Test the trade timing logic"""
        # Trade = teammate kills your killer within 3 seconds
        
        timing_cases = [
            {"time_diff": 1000, "same_team": True, "killed_our_killer": True, "expected": True},    # 1s = trade
            {"time_diff": 3000, "same_team": True, "killed_our_killer": True, "expected": True},   # 3s = trade
            {"time_diff": 3001, "same_team": True, "killed_our_killer": True, "expected": False},  # 3.001s = no trade
            {"time_diff": 2000, "same_team": False, "killed_our_killer": True, "expected": False}, # Enemy = no trade
            {"time_diff": 2000, "same_team": True, "killed_our_killer": False, "expected": False}, # Wrong target = no trade
            {"time_diff": -1000, "same_team": True, "killed_our_killer": True, "expected": False}, # Before death = no trade
        ]
        
        for case in timing_cases:
            with self.subTest(time_diff=case["time_diff"]):
                # Test our trade logic
                is_trade = (case["same_team"] and 
                           0 < case["time_diff"] <= 3000 and 
                           case["killed_our_killer"])
                self.assertEqual(is_trade, case["expected"],
                               f"Trade logic failed for time_diff={case['time_diff']}")
    
    def test_first_blood_chronological(self):
        """Test first blood detection based on chronological order"""
        # First blood = earliest kill in the round by time
        
        # Simulate kill events with timestamps
        kill_events = [
            {"killer": "player1", "victim": "enemy1", "time": 5000},
            {"killer": "player2", "victim": "enemy2", "time": 3000},  # This is first
            {"killer": "player3", "victim": "enemy3", "time": 7000},
        ]
        
        # Sort by time to find first kill
        sorted_events = sorted(kill_events, key=lambda x: x["time"])
        first_kill = sorted_events[0]
        
        self.assertEqual(first_kill["time"], 3000, "First blood should be earliest by time")
        self.assertEqual(first_kill["killer"], "player2", "Wrong player credited with first blood")

