# Henrik API v2 Match Response - Complete Structure

> **Note**: API returned 403 errors during testing (likely temporary issue or key expiration).
> This documentation is based on code analysis, web search, and official documentation.

## Complete Data Structure

### Match Level

```json
{
  "metadata": {
    "matchid": "string",
    "map": "string (e.g., 'Ascent', 'Bind')",
    "game_start": "ISO 8601 timestamp",
    "game_length": "int (seconds)",
    "rounds_played": "int",
    "mode": "string (e.g., 'competitive', 'unrated')",
    "mode_id": "string",
    "queue": "string"
  },
  "players": {
    "all_players": [
      {
        "puuid": "string",
        "name": "string",
        "tag": "string",
        "team": "Red|Blue",
        "character": "string (agent name)",
        "stats": {
          "kills": "int",
          "deaths": "int",
          "assists": "int",
          "headshots": "int",
          "bodyshots": "int",
          "legshots": "int",
          "score": "int (ACS)"
        },
        "damage_made": "int (total damage dealt)",
        "damage_received": "int (total damage taken)",
        "card": "object (player card data)"
      }
    ]
  },
  "teams": {
    "red": {
      "has_won": "boolean",
      "rounds_won": "int"
    },
    "blue": {
      "has_won": "boolean",
      "rounds_won": "int"
    }
  },
  "rounds": [...]
}
```

---

## Round-Level Data (Critical for Advanced Stats)

### Round Structure

```json
{
  "winning_team": "Red|Blue",
  "player_stats": [
    {
      "player_puuid": "string",
      "team": "Red|Blue (sometimes 'player_team')",
      "kills": "int (kills in THIS round)",
      "kill_events": [...],
      "damage_events": [...],
      "economy": {...},
      "ability_casts": {...}
    }
  ],
  "plant_events": [...],
  "defuse_events": [...],
  "plant_location": {...},
  "defuse_location": {...}
}
```

---

## ✅ CONFIRMED: kill_events Structure

**Source**: HenrikDev API documentation & Python API changelog

```json
"kill_events": [
  {
    "kill_time_in_round": 32892,          // milliseconds into the round
    "kill_time_in_match": 87925,          // milliseconds into the match
    "killer_puuid": "string",
    "killer_display_name": "Henrik3#EUW3",
    "killer_team": "Blue|Red",
    "victim_puuid": "string",
    "victim_display_name": "NAMETAG#TAG",
    "victim_team": "Red|Blue",
    "assistants": [                       // CONFIRMED from code
      {
        "puuid": "string"
      }
    ]
  }
]
```

### Additional Fields (Confirmed)
- `damage_weapon_name`: Weapon name (e.g., "Vandal", "Phantom", "Melee") - ✅ USED for knife kill tracking
- `damage_weapon_id`: Weapon UUID/GUID
- `damage_weapon_assets`: Object containing weapon icon URLs

### Additional Fields (Unconfirmed)
- `weapon_guid`: Weapon used (reported as buggy for Chamber abilities, use damage_weapon_name instead)
- `damage`: Damage dealt
- `secondary_fire`: Boolean
- `wallbang`: Boolean (unclear if available)

---

## ✅ CONFIRMED: damage_events Structure

**Source**: HenrikDev API documentation

```json
"damage_events": [
  {
    "receiver_puuid": "string",
    "receiver_display_name": "Henrik3#EUW3",
    "receiver_team": "Red|Blue",
    "bodyshots": 3,                      // shots that hit body in this damage instance
    "damage": 156,                       // total damage in this instance
    "headshots": 1,                      // shots that hit head in this damage instance
    "legshots": 0                        // shots that hit legs in this damage instance
  }
]
```

**Key Insight**: damage_events provides per-instance shot breakdown, not just match totals!

---

## ✅ CONFIRMED: economy Structure

**Source**: Code analysis (currently used by bot)

```json
"economy": {
  "loadout_value": 4500  // total credits spent on weapons/armor this round
}
```

### Additional Economy Fields (Unconfirmed)
- `weapon`: Purchased weapon
- `armor`: Purchased armor
- `remaining`: Credits remaining after buy
- `spent`: Credits spent this round

---

## ✅ CONFIRMED: ability_casts Structure

**Source**: Web search results from HenrikDev API documentation

```json
"ability_casts": {
  "c_casts": 2,  // Ability C uses
  "q_casts": 1,  // Ability Q uses
  "e_casts": 3,  // Ability E uses
  "x_casts": 1   // Ultimate (X) uses
}
```

---

## ✅ CONFIRMED: plant/defuse Events

**Source**: Web search results from HenrikDev API documentation

```json
"plant_events": [
  {
    "player_puuid": "string",
    "plant_location": {
      "x": 1234,
      "y": 5678
    },
    "plant_site": "A|B|C",
    "plant_time_in_round": 45000
  }
],
"defuse_events": [
  {
    "defuser_puuid": "string",
    "defuse_location": {
      "x": 1234,
      "y": 5678
    },
    "defuse_time_in_round": 75000
  }
]
```

---

## Player Locations (Unconfirmed but Likely Available)

**Source**: Web search mentions "player_locations with x, y coordinates and view_radians"

Likely structure:
```json
"player_locations": [
  {
    "player_puuid": "string",
    "x": 1234,
    "y": 5678,
    "view_radians": 3.14
  }
]
```

---

## What's Currently Used by ShootyBot

### ✅ Currently Accessed:
- metadata: matchid, map, game_start, game_length, rounds_played, mode
- players: puuid, name, tag, team, character, stats (K/D/A, headshots/body/legs), damage_made, damage_received
- teams: has_won, rounds_won
- rounds.player_stats: player_puuid, team, kills, kill_events, damage_events, economy
- kill_events: damage_weapon_name (for knife kill tracking)

### 🆕 Available But NOT Used:
- **kill_events**: kill_time_in_match, killer_display_name, killer_team, victim_display_name, victim_team
- **damage_events**: receiver_display_name, receiver_team, bodyshots/headshots/legshots per instance
- **ability_casts**: c_casts, q_casts, e_casts, x_casts (per round)
- **plant_events**: plant location, plant site, plant time
- **defuse_events**: defuse location, defuse time
- **player_locations**: x/y coordinates, view angle

---

## New Stats We Can Calculate

### HIGH PRIORITY (Confirmed Data Available)

#### 1. **Ability Usage Analysis** ✅
```python
# Data: ability_casts {c_casts, q_casts, e_casts, x_casts}
"⚡ **UTILITY KING**: {player} used 45 abilities - maximum impact!"
"🎭 **ULT MASTER**: {player} used ultimate 8 times!"
```

#### 2. **Plant/Defuse Heroes** ✅
```python
# Data: plant_events[], defuse_events[]
"🌱 **SPIKE SPECIALIST**: {player} planted 7/10 rounds!"
"🛠️ **DEFUSE KING**: {player} defused 3 times - clutch saves!"
```

#### 3. **Clutch Detection** ✅
```python
# Data: kill_time, survivor tracking
"🎭 **CLUTCH MASTER**: {player} won 2 clutches (1v3, 1v2)!"
```

#### 4. **Entry Dueling** ✅
```python
# Data: kill_time_in_round for first kills
"⚔️ **ENTRY GOD**: {player} won 5/7 opening duels (71%)!"
```

#### 5. **Eco Performance** ✅
```python
# Data: economy.loadout_value
"💰 **ECO WARRIOR**: {player} - 3 kills on <4k loadout rounds!"
```

#### 6. **Damage Per Instance Analysis** ✅
```python
# Data: damage_events with bodyshots/headshots/legshots per instance
"🎯 **ONE-TAP KING**: {player} averaged 135 damage/kill (efficient!)!"
"😱 **149 CURSE**: {player} dealt 140-149 damage 3 times without the kill!"
```

#### 7. **Team Display Names** ✅
```python
# Data: killer_display_name, victim_display_name in kill_events
# Can show actual names instead of just puuids
```

---

## Data NOT Available

### ❌ Cannot Detect:
- **Spam through smoke** - No smoke position/visibility data
- **Wallbang detection** - Unconfirmed if wallbang flag exists
- **Distance of kills** - Would need player positions at kill time (may be available via player_locations)
- **Flash assists** - No blind/flash effect tracking
- **Angle/positioning quality** - Would need complex position analysis

### ✅ Previously Thought Unavailable (Now Implemented):
- **Knife kills** - ✅ NOW AVAILABLE via `damage_weapon_name` field in kill_events
- **Weapon tracking** - ✅ Available via `damage_weapon_name`, `damage_weapon_id`, and `damage_weapon_assets` (use damage_weapon_name as weapon_guid is buggy)

---

## Recommendations

### Implement First (High Value + Confirmed Data):
1. **Ability usage stats** - Show who's using util effectively
2. **Plant/defuse recognition** - Reward objective play
3. **Clutch detection** - Most exciting for players
4. **Eco round performance** - Highlight skill in tough situations
5. **One-tap/149 damage curse** - Fun and informative

### Implement Next:
6. Entry duel win rate
7. Kill streak tracking
8. Round MVP frequency
9. Damage efficiency analysis
10. Opening duel timing analysis

---

## Notes

- v4 API is recommended over v2 (v2 will be deprecated eventually)
- API sometimes returns 403 even with valid keys (rate limiting or temporary issues)
- Some fields (like weapon_guid) are known to be buggy for certain abilities
- player_locations data needs verification but is mentioned in documentation
