#!/bin/bash

# The name of the screen session
SCREEN_NAME="shooty"


# Source the .bashrc or .bash_profile file
source /home/pi/.bashrc

# Check if the screen session is already running
/usr/bin/screen -list | /bin/grep -q "${SCREEN_NAME}"

# If the screen session is not running, start it
if [ $? -eq 1 ]; then
    /usr/bin/screen -dmS ${SCREEN_NAME} /usr/bin/python3 /home/pi/ShootyBot/ShootyBot/bot.py
fi