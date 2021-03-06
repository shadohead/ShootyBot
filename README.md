# ShootyBot

## Setup

**Prerequisites**

- Python Installed, 3.8 or higher

**Discord Bot Setup**

Follow instructions: https://discordpy.readthedocs.io/en/stable/intro.html

**Run**

Windows:  ```py -3 .\ShootyBot.py```

## Development Guide

- ``ShootyBot.py`` is the main class that is currently responsible for message/react processing. Any new commands must be added to the proper bot event handlers.

- ``UserTracker.py`` is the module responsible for keeping track of SoloQ, Fullstack, and Ready users. 
    - SoloQ users are represented as users willing to play with any number of users
    - Fullstack users are users only willing to play with a full party, default size 5
    - Ready users are users that are currently prepared to play

- ``MessageHandler.py`` is a module dedicated towards constructing and handling message commands. While ``ShootyBot.py`` defines how we process bot events, 
and message construction logic should be written into this module.

- ``DiscordConfig.py`` is a config module dedicated towards static values that are server dependent. Most importantly, you will need to set:
    - Bot Token, from the discord bot application page
    - Role Code, from the discord server that this bot will live