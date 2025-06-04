#!/usr/bin/env python3
"""
Analyze multi-kills based on timing rather than total kills per round
"""

import json
import requests
import os
from collections import defaultdict

def analyze_timing_multikills():
    # Load match data
    match_id = "dae1b62d-c3dd-4663-9131-2771c7f66b5a"
    # API key is pulled from the environment. Set HENRIK_API_KEY in your `.env`
    # file or OS environment before running.
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
    
    print("TIMING-BASED MULTI-KILL ANALYSIS")
    print("="*80)
    
    player_timing_mk = defaultdict(int)
    
    # Analyze each round for timing-based multi-kills
    for round_num, round_data in enumerate(match_data["rounds"]):
        round_events = round_data.get("player_stats", [])
        
        print(f"\nROUND {round_num + 1}:")
        print("-" * 50)
        
        # Collect all kill events with timestamps for this round
        all_kills = []
        for player_round in round_events:
            puuid = player_round["player_puuid"]
            name = player_round["player_display_name"]
            kill_events = player_round.get("kill_events", [])
            
            for kill_event in kill_events:
                kill_time = kill_event.get("kill_time_in_round", 0)
                all_kills.append({
                    "puuid": puuid,
                    "name": name,
                    "time": kill_time,
                    "victim": kill_event.get("victim_display_name", "Unknown")
                })
        
        # Sort kills by time
        all_kills.sort(key=lambda x: x["time"])
        
        # Group kills by player and check for rapid succession
        player_kills = defaultdict(list)
        for kill in all_kills:
            player_kills[kill["puuid"]].append(kill)
        
        # Check each player's kills for rapid succession
        for puuid, kills in player_kills.items():
            if len(kills) >= 2:
                name = kills[0]["name"]
                
                # Check for kills within timing window
                for i in range(len(kills) - 1):
                    time_diff = kills[i + 1]["time"] - kills[i]["time"]
                    
                    print(f"  {name}: Kill #{i+1} -> Kill #{i+2}")
                    print(f"    Time diff: {time_diff/1000:.1f} seconds")
                    print(f"    Kill times: {kills[i]['time']/1000:.1f}s -> {kills[i+1]['time']/1000:.1f}s")
                    print(f"    Victims: {kills[i]['victim']} -> {kills[i+1]['victim']}")
                    
                    # Test different timing windows
                    windows = [3000, 4000, 5000, 6000]  # 3, 4, 5, 6 seconds
                    for window in windows:
                        if time_diff <= window:
                            print(f"    ✓ Multi-kill within {window/1000:.0f}s window")
                        else:
                            print(f"    ✗ Too slow for {window/1000:.0f}s window")
                    print()
    
    print("\n" + "="*80)
    print("MULTI-KILL COUNTS BY TIMING WINDOW")
    print("="*80)
    
    # Test different timing windows
    timing_windows = [3000, 4000, 5000, 6000]  # milliseconds
    
    for window_ms in timing_windows:
        window_sec = window_ms / 1000
        print(f"\n{window_sec:.0f}-SECOND WINDOW RESULTS:")
        print("-" * 50)
        
        player_mk_count = defaultdict(int)
        
        # Recalculate with this timing window
        for round_num, round_data in enumerate(match_data["rounds"]):
            round_events = round_data.get("player_stats", [])
            
            # Collect kills by player
            player_kills = defaultdict(list)
            for player_round in round_events:
                puuid = player_round["player_puuid"]
                name = player_round["player_display_name"]
                kill_events = player_round.get("kill_events", [])
                
                for kill_event in kill_events:
                    kill_time = kill_event.get("kill_time_in_round", 0)
                    player_kills[puuid].append({
                        "name": name,
                        "time": kill_time
                    })
            
            # Check for rapid multi-kills
            for puuid, kills in player_kills.items():
                if len(kills) >= 2:
                    kills.sort(key=lambda x: x["time"])
                    
                    # Check consecutive kills
                    rapid_kills = 1  # Start with first kill
                    for i in range(len(kills) - 1):
                        time_diff = kills[i + 1]["time"] - kills[i]["time"]
                        if time_diff <= window_ms:
                            rapid_kills += 1
                        else:
                            # Reset counter if gap is too long
                            if rapid_kills >= 2:
                                player_mk_count[kills[i]["name"]] += 1
                            rapid_kills = 1
                    
                    # Check final sequence
                    if rapid_kills >= 2:
                        player_mk_count[kills[-1]["name"]] += 1
        
        # Compare with expected values
        print(f"{'Player':<20} {'Calculated':<10} {'Expected':<10} {'Match':<8}")
        print("-" * 50)
        
        all_match = True
        for name in sorted(expected_mk.keys()):
            calculated = player_mk_count.get(name, 0)
            expected = expected_mk[name]
            match = "✓" if calculated == expected else "✗"
            if calculated != expected:
                all_match = False
            
            print(f"{name:<20} {calculated:<10} {expected:<10} {match:<8}")
        
        print(f"\nOVERALL MATCH: {'✓ PERFECT' if all_match else '✗ MISMATCH'}")
        
        if all_match:
            print(f"*** {window_sec:.0f}-SECOND WINDOW MATCHES TRACKER.GG PERFECTLY! ***")
            return window_ms
    
    return None

if __name__ == "__main__":
    perfect_window = analyze_timing_multikills()
    if perfect_window:
        print(f"\nCONCLUSION: Multi-kills are timing-based with {perfect_window/1000:.0f}-second window!")
    else:
        print("\nCONCLUSION: No timing window found that matches perfectly.")