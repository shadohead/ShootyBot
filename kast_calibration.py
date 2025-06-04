#!/usr/bin/env python3
"""
KAST calibration to understand exact differences
"""

import json
import requests
import os
from collections import defaultdict
from calculate_match_stats import get_match_data, calculate_stats

def analyze_kast_differences():
    match_id = "dae1b62d-c3dd-4663-9131-2771c7f66b5a"
    # Get the Henrik API key from the environment. Create a `.env` file or
    # export HENRIK_API_KEY before running this script.
    api_key = os.getenv("HENRIK_API_KEY")
    
    match_data = get_match_data(match_id, api_key)
    calculated_stats = calculate_stats(match_data)
    
    expected_kast = {
        "swu#rango": 68,
        "ewu#KR2": 58,
        "Swoopn#tf2": 63,
        "TwentyJuan123#NA1": 58,
        "Kastostik#erm": 47,
        "Seleção#NA1": 74,
        "xpfc#NA1": 74,
        "Naginata#NA1": 68,
        "Lens#NA1": 84,
        "Foil#001": 74
    }
    
    print("KAST CALIBRATION ANALYSIS")
    print("="*80)
    
    for puuid, stats in calculated_stats.items():
        name = stats["name"]
        if name in expected_kast:
            calculated = stats["kast"]
            expected = expected_kast[name]
            diff = calculated - expected
            kast_rounds = stats.get("kast_rounds", 0)
            
            # Calculate what the KAST rounds should be to match tracker.gg
            target_kast_rounds = round((expected / 100) * 19)  # 19 total rounds
            rounds_adjustment = target_kast_rounds - kast_rounds
            
            print(f"{name:<20} Calc: {calculated:>2}% | Expected: {expected:>2}% | Diff: {diff:+3} | "
                  f"Rounds: {kast_rounds:>2}/19 | Target: {target_kast_rounds:>2} | Adj: {rounds_adjustment:+2}")
    
    print("\n" + "="*80)
    print("ROUND-BY-ROUND KAST ANALYSIS")
    print("="*80)
    
    # Detailed round analysis for problem players
    problem_players = ["ewu#KR2", "Kastostik#erm", "Naginata#NA1", "Lens#NA1", "Foil#001"]
    
    for problem_name in problem_players:
        print(f"\nDETAILED ANALYSIS FOR {problem_name}:")
        print("-" * 50)
        
        # Find player PUUID
        target_puuid = None
        for puuid, stats in calculated_stats.items():
            if stats["name"] == problem_name:
                target_puuid = puuid
                break
        
        if not target_puuid:
            continue
            
        # Analyze each round for this player
        players = {player["puuid"]: player for player in match_data["players"]["all_players"]}
        
        for round_num, round_data in enumerate(match_data["rounds"]):
            round_events = round_data.get("player_stats", [])
            
            # Find this player's round data
            player_round = None
            for pr in round_events:
                if pr["player_puuid"] == target_puuid:
                    player_round = pr
                    break
            
            if not player_round:
                continue
                
            kills = player_round.get("kills", 0)
            
            # Check if player died this round
            died = False
            for event_player in round_events:
                for kill_event in event_player.get("kill_events", []):
                    if kill_event.get("victim_puuid") == target_puuid:
                        died = True
                        break
                if died:
                    break
            
            # Determine KAST status
            kast_status = "NONE"
            if kills > 0:
                kast_status = "KILL"
            elif not died:
                kast_status = "SURVIVE"
            
            print(f"  Round {round_num+1:2}: K={kills} | Died={died} | Status={kast_status}")

if __name__ == "__main__":
    analyze_kast_differences()