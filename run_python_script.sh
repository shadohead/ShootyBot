#!/bin/bash

# The name of the screen session
SCREEN_NAME="shooty"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if the screen session is already running
screen -list | grep -q "${SCREEN_NAME}"

# If the screen session is not running, start it
if [ $? -eq 1 ]; then
    cd "${SCRIPT_DIR}"
    screen -dmS ${SCREEN_NAME} ./run.sh
fi