from datetime import date, datetime
import discord
import pprint
import logging
from discord import player

from discord.ext import commands

logging.basicConfig(level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)

# set bot token here to run
BOT_TOKEN = 'OTMxMDgxNjUzNjE3NTc4MDA3.Yd_PXA.4q2LTLbM6iinp9sKopoCfZt-BP0'
DEFAULT_MSG = "<@&773770148070424657>"  # shooty role code

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!!', intents=intents)

users_who_reacted = set()
users_five_stack_only = set()
latest_bot_message_time = datetime.now()


@bot.event
async def on_ready():
    logging.info('We have logged in as {0.user}'.format(bot))


@bot.event
async def on_message(message):
    global latest_bot_message_time
    if message.author == bot.user and message.content != help_message():
        latest_bot_message_time = message.created_at
        await message.add_reaction('\N{THUMBS UP SIGN}')
        await message.add_reaction('5️⃣')

    # default mode: create new session
    if message.content == ('$shooty') or message.content == ('$s'):
        users_who_reacted.clear
        users_five_stack_only.clear

        await message.channel.send(DEFAULT_MSG)

    # display status
    elif message.content == ('$shooty status') or message.content == ('$ss'):
        await message.channel.send(party_status_message(users_who_reacted, users_five_stack_only))

    elif message.content == ('$shooty clear') or message.content == ('$sc'):
        users_who_reacted.clear
        users_five_stack_only.clear

    elif message.content.startswith('$shooty') or message.content.startswith('$s'):
        await message.channel.send(help_message())


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
        # case: user was in the 5 stack only group
        # remove them from 5 stack group and put them in the regular stack instead
        if user.name in users_five_stack_only:
            users_five_stack_only.remove(user.name)

        users_who_reacted.add(user.name)
        logging.info("stack:" + str(users_who_reacted))

        new_message = party_status_message(
            users_who_reacted, users_five_stack_only)

        await reaction.message.edit(content=new_message)

    # handle 5 stack only players
    elif reaction.emoji == '5️⃣':
        if user.name not in users_who_reacted:
            users_five_stack_only.add(user.name)
            logging.info("5stack:" + str(users_five_stack_only))

        new_message = party_status_message(
            users_who_reacted, users_five_stack_only)

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
    if reaction.emoji == '\N{THUMBS UP SIGN}' and user.name in users_who_reacted:
        users_who_reacted.remove(user.name)

        logging.info("Removed [" + user.name + "] from stack.")
        logging.info("stack:" + str(users_who_reacted))

        # check if user has a 5 stack emoji, if so add them back to that set
        if user in await reaction.message.reactions[1].users().flatten():
            users_five_stack_only.add(user.name)
            logging.info("5stack:" + str(users_who_reacted))

        new_message = party_status_message(
            users_who_reacted, users_five_stack_only)

        await reaction.message.edit(content=new_message)

    # handle 5 stack only players
    elif reaction.emoji == '5️⃣' and user.name in users_five_stack_only:
        users_five_stack_only.remove(user.name)
        logging.info("Removed [" + user.name + "] from 5 stack.")
        logging.info("5stack:" + str(users_five_stack_only))

        new_message = party_status_message(
            users_who_reacted, users_five_stack_only)

        await reaction.message.edit(content=new_message)


def party_status_message(player_set, five_stack_set):
    if len(player_set)+len(five_stack_set) >= 5:
        new_message = DEFAULT_MSG + "\n\n"\
            + bold(str(len(player_set)+len(five_stack_set))) + bold("/5")\
            + "\n" + pretty_player_sets(player_set, five_stack_set)
    elif player_set and five_stack_set:
        new_message = DEFAULT_MSG + "\n\n"\
            + bold(str(len(player_set))) + "(" + str(len(five_stack_set)) + ")" + bold("/5")\
            + "\n" + pretty_player_sets(player_set, five_stack_set)
    elif player_set:
        new_message = DEFAULT_MSG + "\n\n"\
            + bold(str(len(player_set)) + "/5")\
            + "\n" + pretty_player_sets(player_set, five_stack_set)
    elif five_stack_set:
        new_message = DEFAULT_MSG + "\n\n"\
            + "(" + str(len(five_stack_set)) + ")" + bold("/5")\
            + "\n" + pretty_player_sets(player_set, five_stack_set)
    else:
        new_message = "" + DEFAULT_MSG + "\n\n"\
            + "sadge/5"

    return new_message


def pretty_player_sets(player_set, five_stack_set):
    result_string = ''

    for index, player in enumerate(player_set):
        result_string += bold(player)

        # if it's not the last player, add a comma
        if index < len(player_set) + len(five_stack_set) - 1:
            result_string += ", "

    for index, player in enumerate(five_stack_set):
        result_string += italics(player)

        # if it's not the last player, add a comma
        if index < len(five_stack_set) - 1:
            result_string += ", "

    return result_string


def bold(input):
    return "**" + input + "**"


def italics(input):
    return "*" + input + "*"


def help_message():
    return "ShootyBot help:" + "\n\n"\
        + "*$shooty* or *$s* -- Starts new Shooty session \n" \
        + "*$shooty status* or *$ss* -- Shows current Shooty session status \n"\
        + "*$shooty clear* or *$sc* -- Clears current Shooty session"


bot.run(BOT_TOKEN)
