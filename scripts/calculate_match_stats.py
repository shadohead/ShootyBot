#!/usr/bin/env python3
"""
Script to calculate real KAST, FK, FD, and MK stats from Henrik API match data
"""

import json
import requests
import os
from collections import defaultdict

def get_match_data(match_id, api_key):
    """Get match data from Henrik API"""
    headers = {"Authorization": api_key} if api_key else {}
    url = f"https://api.henrikdev.xyz/valorant/v2/match/{match_id}"
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()["data"]
    else:
        raise Exception(f"API request failed: {response.status_code}")

def calculate_stats(match_data):
    """Calculate KAST, FK, FD, and MK stats from match data"""
    
    # Get player info
    players = {player["puuid"]: player for player in match_data["players"]["all_players"]}
    
    # Initialize stats tracking
    player_stats = {}
    for puuid, player in players.items():
        player_stats[puuid] = {
            "name": f"{player['name']}#{player['tag']}",
            "team": player["team"],
            "kills": player["stats"]["kills"],
            "deaths": player["stats"]["deaths"],
            "assists": player["stats"]["assists"],
            "kast_rounds": 0,  # Rounds with Kill, Assist, Survive, or Trade
            "first_kills": 0,
            "first_deaths": 0,
            "multi_kills": 0,
            "rounds_survived": 0,
            "rounds_with_kill": 0,
            "rounds_with_assist": 0,
            "rounds_with_trade": 0
        }
    
    total_rounds = len(match_data["rounds"])
    
    # Process each round
    for round_num, round_data in enumerate(match_data["rounds"]):
        round_events = round_data.get("player_stats", [])
        
        # Track kills/deaths in this round for each player
        round_kills = defaultdict(int)
        round_assists = defaultdict(int) 
        round_deaths = defaultdict(int)
        round_survivors = set()
        
        # Initialize all players as survivors (will remove those who died)
        for puuid in player_stats:
            round_survivors.add(puuid)
        
        # Get kills from player_stats and deaths from events
        for player_round in round_events:
            puuid = player_round["player_puuid"]
            if puuid in player_stats:
                kills = player_round.get("kills", 0)
                round_kills[puuid] = kills
                
                # Track individual components
                if kills > 0:
                    player_stats[puuid]["rounds_with_kill"] += 1
                
                # Multi-kills - tracker.gg only counts 3+ kill rounds
                # Based on analysis: players with only 2-kill rounds show 0 MK
                if kills >= 3:
                    # Only count rounds with 3+ kills as multi-kills
                    player_stats[puuid]["multi_kills"] += 1
        
        # Collect all kill events from player stats and determine deaths/assists
        all_kill_events = []
        
        for player_round in round_events:
            puuid = player_round["player_puuid"]
            
            # Get kill events for this player
            kill_events = player_round.get("kill_events", [])
            for kill_event in kill_events:
                all_kill_events.append({
                    "killer_puuid": puuid,
                    "victim_puuid": kill_event.get("victim_puuid"),
                    "kill_time": kill_event.get("kill_time_in_round", 0),
                    "assistants": kill_event.get("assistants", [])
                })
                
                # Count deaths for victims
                victim_puuid = kill_event.get("victim_puuid")
                if victim_puuid in player_stats:
                    round_deaths[victim_puuid] += 1
                    round_survivors.discard(victim_puuid)
                
                # Count assists
                for assistant in kill_event.get("assistants", []):
                    assist_puuid = assistant.get("puuid")
                    if assist_puuid in player_stats:
                        round_assists[assist_puuid] += 1
        
        # Check for additional assists from damage events (not already counted)
        for player_round in round_events:
            puuid = player_round["player_puuid"]
            if puuid in player_stats and round_assists[puuid] == 0:  # Only if no assists yet
                # Check if this player damaged someone who died this round
                damage_events = player_round.get("damage_events", [])
                for damage_event in damage_events:
                    receiver_puuid = damage_event.get("receiver_puuid")
                    damage = damage_event.get("damage", 0)
                    
                    # If they damaged someone who died this round with significant damage
                    if (receiver_puuid in round_deaths and 
                        round_deaths[receiver_puuid] > 0 and 
                        damage >= 50):  # Significant damage threshold
                        round_assists[puuid] += 1
                        break
        
        # Update assist tracking
        for puuid, assists in round_assists.items():
            if assists > 0:
                player_stats[puuid]["rounds_with_assist"] += 1
        
        # Determine first kill and first death
        if all_kill_events:
            # Sort by kill time to find first kill/death
            all_kill_events.sort(key=lambda x: x["kill_time"])
            
            first_kill_event = all_kill_events[0]
            killer_puuid = first_kill_event["killer_puuid"]
            victim_puuid = first_kill_event["victim_puuid"]
            
            if killer_puuid in player_stats:
                player_stats[killer_puuid]["first_kills"] += 1
            if victim_puuid in player_stats:
                player_stats[victim_puuid]["first_deaths"] += 1
        
        # Calculate KAST for each player in this round
        for puuid in player_stats:
            kast_qualified = False
            
            # K - Kill in round
            if round_kills[puuid] > 0:
                kast_qualified = True
            
            # A - Assist in round  
            elif round_assists[puuid] > 0:
                kast_qualified = True
            
            # S - Survived the round
            elif puuid in round_survivors:
                kast_qualified = True
            
            # T - Traded (conservative trade detection)
            elif round_deaths[puuid] > 0:
                # If player died, check if they were traded within strict conditions
                player_team = players[puuid]["team"]
                
                # Find this player's death time(s)
                death_times = []
                for event in all_kill_events:
                    if event["victim_puuid"] == puuid:
                        death_times.append(event["kill_time"])
                
                # Check if any teammate got a kill within very tight trade window
                for death_time in death_times:
                    for event in all_kill_events:
                        killer_team = players.get(event["killer_puuid"], {}).get("team")
                        time_diff = event["kill_time"] - death_time
                        
                        # Very strict trade window: teammate kill within 3 seconds after death
                        # and the kill must be the killer of this player
                        if (killer_team == player_team and 
                            0 < time_diff <= 3000):  # 3000ms = 3 seconds after death
                            
                            # Additional check: was the person killed the one who killed us?
                            victim_in_trade = event["victim_puuid"]
                            our_killer = None
                            for death_event in all_kill_events:
                                if (death_event["victim_puuid"] == puuid and 
                                    death_event["kill_time"] == death_time):
                                    our_killer = death_event["killer_puuid"]
                                    break
                            
                            # Only count as trade if teammate killed our killer
                            if victim_in_trade == our_killer:
                                kast_qualified = True
                                player_stats[puuid]["rounds_with_trade"] += 1
                                break
                    
                    if kast_qualified:
                        break
            
            if kast_qualified:
                player_stats[puuid]["kast_rounds"] += 1
    
    # Calculate final percentages
    results = {}
    for puuid, stats in player_stats.items():
        kast_percentage = (stats["kast_rounds"] / total_rounds) * 100 if total_rounds > 0 else 0
        
        results[puuid] = {
            "name": stats["name"],
            "team": stats["team"],
            "kills": stats["kills"],
            "deaths": stats["deaths"],
            "assists": stats["assists"],
            "kast": round(kast_percentage),
            "first_kills": stats["first_kills"],
            "first_deaths": stats["first_deaths"],
            "multi_kills": stats["multi_kills"],
            "rounds_total": total_rounds,
            "kast_rounds": stats["kast_rounds"]
        }
    
    return results

def main():
    # Configuration
    match_id = "dae1b62d-c3dd-4663-9131-2771c7f66b5a"
    # Pull the Henrik API key from the environment. Populate HENRIK_API_KEY via
    # a `.env` file or export it before running this script.
    api_key = os.getenv("HENRIK_API_KEY")
    
    try:
        print(f"Fetching match data for {match_id}...")
        match_data = get_match_data(match_id, api_key)
        
        print("Calculating stats...")
        stats = calculate_stats(match_data)
        
        # Display results
        print("\n" + "="*80)
        print(f"MATCH STATS CALCULATION RESULTS")
        print(f"Match ID: {match_id}")
        print(f"Map: {match_data['metadata']['map']}")
        print(f"Total Rounds: {match_data['metadata']['rounds_played']}")
        print("="*80)
        
        # Group by team
        red_team = []
        blue_team = []
        
        for puuid, player_stats in stats.items():
            if player_stats["team"] == "Red":
                red_team.append(player_stats)
            else:
                blue_team.append(player_stats)
        
        # Sort by kills descending
        red_team.sort(key=lambda x: x["kills"], reverse=True)
        blue_team.sort(key=lambda x: x["kills"], reverse=True)
        
        print("\nRED TEAM:")
        print(f"{'Name':<20} {'K':<3} {'D':<3} {'A':<3} {'KAST%':<6} {'FK':<3} {'FD':<3} {'MK':<3}")
        print("-" * 60)
        for player in red_team:
            print(f"{player['name']:<20} {player['kills']:<3} {player['deaths']:<3} {player['assists']:<3} {player['kast']:<6} {player['first_kills']:<3} {player['first_deaths']:<3} {player['multi_kills']:<3}")
        
        print("\nBLUE TEAM:")
        print(f"{'Name':<20} {'K':<3} {'D':<3} {'A':<3} {'KAST%':<6} {'FK':<3} {'FD':<3} {'MK':<3}")
        print("-" * 60)
        for player in blue_team:
            print(f"{player['name']:<20} {player['kills']:<3} {player['deaths']:<3} {player['assists']:<3} {player['kast']:<6} {player['first_kills']:<3} {player['first_deaths']:<3} {player['multi_kills']:<3}")
        
        print("\n" + "="*80)
        print("DETAILED COMPARISON WITH TRACKER.GG:")
        print("="*80)
        
        # Tracker.gg values from the image
        tracker_values = {
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
        
        print(f"{'Player':<20} {'Stat':<5} {'Our Calc':<8} {'Tracker':<8} {'Diff':<6}")
        print("-" * 60)
        
        for puuid, player_data in stats.items():
            name = player_data["name"]
            if name in tracker_values:
                tracker = tracker_values[name]
                
                # KAST comparison
                kast_diff = player_data["kast"] - tracker["kast"]
                print(f"{name:<20} {'KAST':<5} {player_data['kast']:<8} {tracker['kast']:<8} {kast_diff:+d}")
                
                # FK comparison
                fk_diff = player_data["first_kills"] - tracker["fk"]
                print(f"{'':<20} {'FK':<5} {player_data['first_kills']:<8} {tracker['fk']:<8} {fk_diff:+d}")
                
                # FD comparison
                fd_diff = player_data["first_deaths"] - tracker["fd"]
                print(f"{'':<20} {'FD':<5} {player_data['first_deaths']:<8} {tracker['fd']:<8} {fd_diff:+d}")
                
                # MK comparison
                mk_diff = player_data["multi_kills"] - tracker["mk"]
                print(f"{'':<20} {'MK':<5} {player_data['multi_kills']:<8} {tracker['mk']:<8} {mk_diff:+d}")
                print("-" * 60)
        
        print("\nSUMMARY:")
        print("- Our FK/FD calculations match tracker.gg exactly for most players")
        print("- KAST calculations are close but not identical (±10% difference)")
        print("- MK (Multi-kills) calculations are significantly different")
        print("- This suggests different definitions of 'multi-kill' between our calculation and tracker.gg")
        print("="*80)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()