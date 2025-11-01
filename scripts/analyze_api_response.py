#!/usr/bin/env python3
"""
Script to fetch real Henrik API match data and analyze the full response structure
to understand what fields are actually available for stats calculation.
"""

import json
import requests
import os
import sys


def get_match_data(match_id, api_key):
    """Get match data from Henrik API v2 endpoint"""
    headers = {"Authorization": api_key} if api_key else {}
    url = f"https://api.henrikdev.xyz/valorant/v2/match/{match_id}"

    print(f"Fetching match data from: {url}")
    print(f"Using API key: {'Yes' if api_key else 'No'}")

    response = requests.get(url, headers=headers, timeout=30)
    print(f"Response status: {response.status_code}")

    if response.status_code == 200:
        return response.json()["data"]
    else:
        raise Exception(f"API request failed: {response.status_code} - {response.text}")


def analyze_structure(data, prefix="", max_depth=4, current_depth=0):
    """Recursively analyze data structure and print available fields"""
    if current_depth >= max_depth:
        return

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                print(f"{prefix}{key}: {{...}} (dict with {len(value)} keys)")
            elif isinstance(value, list):
                if len(value) > 0:
                    print(f"{prefix}{key}: [...] (list with {len(value)} items)")
                    if isinstance(value[0], dict):
                        print(f"{prefix}  └─ [0]: {{...}} (sample item)")
                        analyze_structure(value[0], prefix + "    ", max_depth, current_depth + 1)
                    else:
                        print(f"{prefix}  └─ [0]: {type(value[0]).__name__} = {value[0]}")
                else:
                    print(f"{prefix}{key}: [] (empty list)")
            else:
                value_str = str(value)[:50] if value is not None else "None"
                print(f"{prefix}{key}: {type(value).__name__} = {value_str}")
    elif isinstance(data, list):
        for i, item in enumerate(data[:2]):  # Only show first 2 items
            print(f"{prefix}[{i}]:")
            analyze_structure(item, prefix + "  ", max_depth, current_depth + 1)


def analyze_kill_event(kill_event):
    """Deep dive into a single kill event to see all available fields"""
    print("\n" + "="*80)
    print("DETAILED KILL EVENT STRUCTURE")
    print("="*80)
    print(json.dumps(kill_event, indent=2))


def analyze_damage_event(damage_event):
    """Deep dive into a single damage event to see all available fields"""
    print("\n" + "="*80)
    print("DETAILED DAMAGE EVENT STRUCTURE")
    print("="*80)
    print(json.dumps(damage_event, indent=2))


def analyze_player_round_stats(player_stats):
    """Deep dive into player round stats"""
    print("\n" + "="*80)
    print("DETAILED PLAYER ROUND STATS STRUCTURE")
    print("="*80)
    print(json.dumps(player_stats, indent=2))


def main():
    # Configuration
    match_id = "dae1b62d-c3dd-4663-9131-2771c7f66b5a"
    api_key = sys.argv[1] if len(sys.argv) > 1 else os.getenv("HENRIK_API_KEY")

    if not api_key:
        print("ERROR: No API key provided!")
        print("Usage: python analyze_api_response.py <API_KEY>")
        print("   or: export HENRIK_API_KEY=<API_KEY>")
        sys.exit(1)

    try:
        print("="*80)
        print("FETCHING MATCH DATA FROM HENRIK API")
        print("="*80)

        match_data = get_match_data(match_id, api_key)

        print("\n" + "="*80)
        print("TOP-LEVEL STRUCTURE")
        print("="*80)
        analyze_structure(match_data, "", max_depth=1)

        print("\n" + "="*80)
        print("METADATA STRUCTURE")
        print("="*80)
        if 'metadata' in match_data:
            analyze_structure(match_data['metadata'], "  ")

        print("\n" + "="*80)
        print("TEAMS STRUCTURE")
        print("="*80)
        if 'teams' in match_data:
            analyze_structure(match_data['teams'], "  ")

        print("\n" + "="*80)
        print("SAMPLE PLAYER STRUCTURE (players.all_players[0])")
        print("="*80)
        if 'players' in match_data and 'all_players' in match_data['players']:
            if len(match_data['players']['all_players']) > 0:
                analyze_structure(match_data['players']['all_players'][0], "  ", max_depth=2)

        print("\n" + "="*80)
        print("SAMPLE ROUND STRUCTURE (rounds[0])")
        print("="*80)
        if 'rounds' in match_data and len(match_data['rounds']) > 0:
            round_data = match_data['rounds'][0]

            # Show top-level round structure
            print("Round keys:", list(round_data.keys()))

            # Analyze player_stats in round
            if 'player_stats' in round_data and len(round_data['player_stats']) > 0:
                print("\n--- Sample player_stats[0] in round ---")
                player_stats = round_data['player_stats'][0]

                # Show all keys first
                print("Available keys in player_stats:")
                for key in sorted(player_stats.keys()):
                    print(f"  - {key}")

                # Deep dive into specific important fields
                if 'kill_events' in player_stats and len(player_stats['kill_events']) > 0:
                    print("\n--- kill_events[0] ---")
                    analyze_kill_event(player_stats['kill_events'][0])

                if 'damage_events' in player_stats and len(player_stats['damage_events']) > 0:
                    print("\n--- damage_events[0] ---")
                    analyze_damage_event(player_stats['damage_events'][0])

                # Show the full player_stats for one player
                analyze_player_round_stats(player_stats)

        # Check for plant/defuse events
        print("\n" + "="*80)
        print("CHECKING FOR PLANT/DEFUSE EVENTS")
        print("="*80)
        if 'rounds' in match_data:
            for i, round_data in enumerate(match_data['rounds'][:3]):  # Check first 3 rounds
                print(f"\nRound {i+1} keys: {list(round_data.keys())}")

                if 'plant_events' in round_data:
                    print(f"  ✓ Has plant_events: {len(round_data['plant_events'])} events")
                    if len(round_data['plant_events']) > 0:
                        print(f"    Sample: {json.dumps(round_data['plant_events'][0], indent=6)}")

                if 'defuse_events' in round_data:
                    print(f"  ✓ Has defuse_events: {len(round_data['defuse_events'])} events")
                    if len(round_data['defuse_events']) > 0:
                        print(f"    Sample: {json.dumps(round_data['defuse_events'][0], indent=6)}")

                if 'plant_location' in round_data:
                    print(f"  ✓ Has plant_location: {round_data['plant_location']}")

                if 'defuse_location' in round_data:
                    print(f"  ✓ Has defuse_location: {round_data['defuse_location']}")

        # Save full response to file for reference
        output_file = "henrik_api_full_response.json"
        with open(output_file, 'w') as f:
            json.dump(match_data, f, indent=2)
        print(f"\n✓ Full response saved to: {output_file}")

        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
