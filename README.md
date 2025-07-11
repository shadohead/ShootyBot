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
    - Role Code, from the discord server that this bot will live⌊‣祓瑳浥⁤敄汰祯敭瑮ਊ潆⁲敲楬扡敬瀠潲畤瑣潩⁮獵条⁥潹⁵慣⁮畲⁮桓潯祴潂⁴湵敤⁲祳瑳浥⁤湩瑳慥⁤景琠敨氊来捡⁹牣湯猯牣敥⁮灡牰慯档ਮ怊恠慢桳⌊椠獮慴汬甠楮⁴楦敬⁳爨湵愠⁳潲瑯਩⼮敳畴彰祳瑳浥⹤桳㰠潢⵴獵牥ਾ恠੠吊楨⁳湩瑳污獬਺‭獠潨瑯批瑯献牥楶散⁠桷捩⁨敫灥⁳桴⁥潢⁴畲湮湩⁧湡⁤敲瑳牡獴椠⁴湯映楡畬敲ⴊ怠桳潯祴潢⵴灵慤整琮浩牥⁠桷捩⁨牴杩敧獲搠楡祬甠摰瑡⁥档捥獫ਊ潌獧愠敲愠慶汩扡敬瘠慩怠潪牵慮捬汴ⴠ⁵桳潯祴潢⹴敳癲捩恥ਮ敓⁥桴⁥楦敬⁳湩怠敤汰祯怯映牯琠浥汰瑡獥ਮ