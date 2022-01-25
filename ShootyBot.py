from datetime import date, datetime
import discord
import pprint
import logging
from discord import player
from DiscordConfig import *
from EventHandler.MessageHandler import *
from UserTracker import *

from discord.ext import commands

logging.basicConfig(level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!!', intents=intents)

latest_bot_message_time = datetime.now()
latest_shooty_session_time = 0

@bot.event
async def on_ready():
    logging.info('We have logged in as {0.user}'.format(bot))


@bot.event
async def on_message(message):
    global latest_bot_message_time
    global party_max_size

    # ensure bot only adds reaction emojis to messages by itself and containing the default message
    if message.author == bot.user and message.content.startswith(DEFAULT_MSG):
        latest_bot_message_time = message.created_at
        await add_react_options(message)

    # default mode: create new session
    if message.content == ('$shooty') or message.content == ('$st'):
        logging.info("Starting new shooty session")
        latest_shooty_session_time = datetime.now()
        reset_users()
        await ping_shooty(message.channel)

    # display status
    elif message.content == ('$shooty status') or message.content == ('$sts'):
        logging.info("Printing Status")
        await send_party_status_message(message.channel)

    # clear the user sets
    elif message.content == ('$shooty clear') or message.content == ('$stc'):
        logging.info("Clearing user sets: " +
                     str(to_names_list(bot_soloq_user_set.union(bot_fullstack_user_set))))
        reset_users()
        await message.channel.send("Cleared shooty session.")

    # mention all reactors
    elif message.content == ('$shooty mention') or message.content == ('$stm'):
        await mention_reactors(message)

    # remove the person from both groups
    elif message.content.startswith('$shooty kick'):
        split_message = message.content.split()
        user_names_list = split_message[2:]
        kicked_usernames_list = remove_user_from_everything(user_names_list)
        
        await send_kicked_user_message(message.channel, kicked_usernames_list)

    elif message.content.startswith('$stk'):
        split_message = message.content.split()
        user_names_list = split_message[1:]
        kicked_usernames_list = remove_user_from_everything(user_names_list)

        await send_kicked_user_message(message.channel, kicked_usernames_list)
    
    elif message.content.startswith('$shooty size'):
        split_message = message.content.split()

        if len(split_message) >= 3 and split_message[2].isdigit():
            logging.info("Changing size to: " + str(split_message[2]))
            new_party_max_size = int(split_message[2])
            set_party_max_size(new_party_max_size)

        await send_max_party_size_message(message.channel)

    # display help message
    elif message.content.startswith('$shooty') or message.content.startswith('$st'):
        await send_help_message(message.channel)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot or reaction.message.author != bot.user:
        return

    if reaction.message.created_at < latest_bot_message_time:
        logging.info(
            "Ignore react since it is not on the latest shootyBot message")
        return

    # handle main group of players
    if reaction.emoji == '\N{THUMBS UP SIGN}':
        # case: user was in the full stack only group and wanted to join the regular group
        # remove them from full stack group and put them in the regular group instead
        remove_fullstack_user(user)
        add_soloq_user(user)
        logging.info("stack:" + str(to_names_list(bot_soloq_user_set)))

        new_message = party_status_message(True)
        await reaction.message.edit(content=new_message)

    # handle full stack only players
    elif reaction.emoji == '5️⃣':
        if not is_soloq_user(user):
            add_fullstack_user(user)
            logging.info("fullstack:" + str(to_names_list(bot_fullstack_user_set)))

        new_message = party_status_message(True)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        bot_ready_user_set.add(user)
        logging.info("ready_set:" + str(to_names_list(bot_ready_user_set)))

        new_message = party_status_message(True)

        await reaction.message.edit(content=new_message)


@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot or reaction.message.author != bot.user:
        return

    if reaction.message.created_at < latest_bot_message_time:
        logging.info(
            "Ignore react since it is not on the latest shootyBot message")
        return

    # handle main group of players
    if reaction.emoji == '\N{THUMBS UP SIGN}' and is_soloq_user(user):
        remove_soloq_user(user)

        logging.info("Removed [" + user.name + "] from stack.")
        logging.info("stack:" + str(to_names_list(bot_soloq_user_set)))

        # case: user removed themselves from the regular group, but still has a react for the full stack
        # check if user has a full stack emoji react, if so add them back to that set
        if user in await reaction.message.reactions[1].users().flatten():
            add_fullstack_user(user)
            logging.info("fullstack:" + str(to_names_list(bot_soloq_user_set)))

        new_message = party_status_message(True)

        await reaction.message.edit(content=new_message)

    # handle full stack only players
    elif reaction.emoji == '5️⃣' and user in bot_fullstack_user_set:
        remove_fullstack_user(user)
        logging.info("Removed [" + user.name + "] from full stack.")
        logging.info("fullstack:" + str(to_names_list(bot_fullstack_user_set)))

        new_message = party_status_message(True)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        bot_ready_user_set.remove(user)
        logging.info("ready_set:" + str(to_names_list(bot_ready_user_set)))

        new_message = party_status_message(True)

        await reaction.message.edit(content=new_message)

# Logger helper
def to_names_list(user_set):
    result_list = []
    for user in user_set:
        result_list.append(user.name)
    return result_list


bot.run(BOT_TOKEN)
