#!/usr/bin/env python3
"""
Analyze multi-kill patterns to understand tracker.gg's definition
"""

import json
import requests
import os
from collections import defaultdict

def analyze_multikills():
    # Load match data
    match_id = "dae1b62d-c3dd-4663-9131-2771c7f66b5a"
    # Load your Henrik API key from the environment for security. Provide this
    # via a `.env` file or regular environment variables.
    api_key = os.getenv("HENRIK_API_KEY")
    
    headers = {"Authorization": api_key}
    url = f"https://api.henrikdev.xyz/valorant/v2/match/{match_id}"
    
    response = requests.get(url, headers=headers)
    match_data = response.json()["data"]
    
    # Expected MK values from tracker.gg
    expected_mk = {
        "swu#rango": 1,
        "ewu#KR2": 1,
        "Swoopn#tf2": 1,
        "TwentyJuan123#NA1": 1,
        "Kastostik#erm": 0,
        "Seleção#NA1": 3,
        "xpfc#NA1": 0,
        "Naginata#NA1": 0,
        "Lens#NA1": 0,
        "Foil#001": 0
    }
    
    print("MULTI-KILL ANALYSIS")
    print("="*80)
    
    # Analyze each player's kill patterns
    for round_num, round_data in enumerate(match_data["rounds"]):
        round_events = round_data.get("player_stats", [])
        
        print(f"\nROUND {round_num + 1}:")
        print("-" * 40)
        
        for player_round in round_events:
            name = player_round["player_display_name"]
            kills = player_round.get("kills", 0)
            
            if kills >= 2:
                expected = expected_mk.get(name, "?")
                print(f"{name:<20} {kills} kills (expected MK: {expected})")
    
    print("\n" + "="*80)
    print("SUMMARY BY PLAYER:")
    print("="*80)
    
    # Count rounds with 2+ kills for each player
    player_multikill_rounds = defaultdict(list)
    total_kills_by_player = defaultdict(int)
    
    for round_num, round_data in enumerate(match_data["rounds"]):
        round_events = round_data.get("player_stats", [])
        
        for player_round in round_events:
            name = player_round["player_display_name"]
            kills = player_round.get("kills", 0)
            total_kills_by_player[name] += kills
            
            if kills >= 2:
                player_multikill_rounds[name].append((round_num + 1, kills))
    
    for name in sorted(expected_mk.keys()):
        expected = expected_mk[name]
        rounds_with_mk = player_multikill_rounds.get(name, [])
        total_mk_rounds = len(rounds_with_mk)
        total_kills = total_kills_by_player.get(name, 0)
        
        print(f"{name:<20} Total Kills: {total_kills:<3} MK Rounds: {total_mk_rounds:<2} Expected MK: {expected}")
        for round_num, kills in rounds_with_mk:
            print(f"  Round {round_num}: {kills} kills")
    
    print("\n" + "="*80)
    print("ANALYSIS:")
    print("- Players with 0 expected MK have multi-kill rounds but tracker.gg shows 0")
    print("- This suggests tracker.gg might not count certain types of multi-kills")
    print("- Or they might have a minimum threshold (e.g., only 3+ kills count)")
    print("- Or they might count specific multi-kill achievements differently")

if __name__ == "__main__":
    analyze_multikills()