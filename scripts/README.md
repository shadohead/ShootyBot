# Development & Analysis Scripts

This directory contains development and analysis scripts used during bot development and API reverse engineering.

## Scripts

### Match Analysis & Calibration

- **`analyze_multikills.py`** - Analysis script for understanding multi-kill detection patterns in Valorant matches
- **`analyze_timing_multikills.py`** - Time-based analysis of multi-kill events to reverse engineer tracker.gg calculations
- **`kast_calibration.py`** - KAST (Kill/Assist/Survive/Trade) calculation calibration against tracker.gg ground truth
- **`calculate_match_stats.py`** - Comprehensive match statistics calculator for testing Henrik API data processing

## Purpose

These scripts were used to achieve 100% accuracy with tracker.gg statistics by:
1. Creating ground truth datasets from verified sources
2. Reverse engineering complex stat calculations (KAST, multi-kills, first bloods)
3. Testing hypotheses about API data structures
4. Validating calculation accuracy against production data

## Usage

These scripts are for development reference and are not required for bot operation. They can be safely ignored during normal bot deployment.

For historical context on the reverse engineering process, see CLAUDE.md section "Advanced Valorant Statistics & API Analysis".
