from datetime import date, datetime
import discord
import pprint
import logging
from discord import player

from discord.ext import commands

logging.basicConfig(level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)

# set bot token here to run
BOT_TOKEN = ''
DEFAULT_MSG = "<@&773770148070424657>"  # shooty role code

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!!', intents=intents)

user_set = set()  # set with all the users in the shooty crew
user_5_set = set()  # set with all the 5 stack only users in the shooty crew
latest_bot_message_time = datetime.now()


@bot.event
async def on_ready():
    logging.info('We have logged in as {0.user}'.format(bot))


@bot.event
async def on_message(message):
    global latest_bot_message_time

    # ensure bot only adds reaction emojis to messages by itself and containing the default message
    if message.author == bot.user and message.content.startswith(DEFAULT_MSG):
        latest_bot_message_time = message.created_at
        await message.add_reaction('\N{THUMBS UP SIGN}')
        await message.add_reaction('5️⃣')

    # default mode: create new session
    if message.content == ('$shooty') or message.content == ('$st'):
        user_set.clear
        user_5_set.clear

        await message.channel.send(DEFAULT_MSG)

    # display status
    elif message.content == ('$shooty status') or message.content == ('$sts'):
        await message.channel.send(party_status_message(user_set, user_5_set))

    # clear the user sets
    elif message.content == ('$shooty clear') or message.content == ('$stc'):
        user_set.clear
        user_5_set.clear
        await message.channel.send("Cleared shooty session.")

    # mention all reactors
    elif message.content == ('$shooty mention') or message.content == ('$stm'):
        await mention_reactors(message)

    # display help message
    elif message.content.startswith('$shooty') or message.content.startswith('$st'):
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
        # case: user was in the 5 stack only group and wanted to join the regular group
        # remove them from 5 stack group and put them in the regular group instead
        if user in user_5_set:
            user_5_set.remove(user)

        user_set.add(user)
        logging.info("stack:" + str(names_list(user_set)))

        new_message = party_status_message(
            user_set, user_5_set)

        await reaction.message.edit(content=new_message)

    # handle 5 stack only players
    elif reaction.emoji == '5️⃣':
        if user not in user_set:
            user_5_set.add(user)
            logging.info("5stack:" + str(names_list(user_5_set)))

        new_message = party_status_message(
            user_set, user_5_set)

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
    if reaction.emoji == '\N{THUMBS UP SIGN}' and user in user_set:
        user_set.remove(user)

        logging.info("Removed [" + user.name + "] from stack.")
        logging.info("stack:" + str(names_list(user_set)))

        # case: user removed themselves from the regular group, but still has a react for the 5 stack
        # check if user has a 5 stack emoji react, if so add them back to that set
        if user in await reaction.message.reactions[1].users().flatten():
            user_5_set.add(user)
            logging.info("5stack:" + str(names_list(user_set)))

        new_message = party_status_message(
            user_set, user_5_set)

        await reaction.message.edit(content=new_message)

    # handle 5 stack only players
    elif reaction.emoji == '5️⃣' and user in user_5_set:
        user_5_set.remove(user)
        logging.info("Removed [" + user.name + "] from 5 stack.")
        logging.info("5stack:" + str(names_list(user_5_set)))

        new_message = party_status_message(
            user_set, user_5_set)

        await reaction.message.edit(content=new_message)

# Sends message mentioning everyone in the shooty crew
async def mention_reactors(message):
    if not user_set and not user_5_set:
        await message.channel.send("No shooty boys to mention.")
        return

    mention_message = ''
    regular_stack_reactors = user_set
    five_stack_reactors = user_5_set
    for user in regular_stack_reactors.union(five_stack_reactors):
        if not user.bot:
            mention_message += user.mention + " "

    await message.channel.send(mention_message)


# String formatted with status of the shooty crew
def party_status_message(player_set, five_stack_set):

    if len(player_set)+len(five_stack_set) >= 5:
        new_message = DEFAULT_MSG + "\n\n"\
            + bold(str(len(player_set)+len(five_stack_set))) + bold("/5")\
            + "\n" + \
            pretty_player_sets(names_list(player_set),
                               names_list(five_stack_set))
    elif player_set and five_stack_set:
        new_message = DEFAULT_MSG + "\n\n"\
            + bold(str(len(player_set))) + "(" + str(len(five_stack_set)) + ")" + bold("/5")\
            + "\n" + \
            pretty_player_sets(names_list(player_set),
                               names_list(five_stack_set))
    elif player_set:
        new_message = DEFAULT_MSG + "\n\n"\
            + bold(str(len(player_set)) + "/5")\
            + "\n" + \
            pretty_player_sets(names_list(player_set),
                               names_list(five_stack_set))
    elif five_stack_set:
        new_message = DEFAULT_MSG + "\n\n"\
            + "(" + str(len(five_stack_set)) + ")" + bold("/5")\
            + "\n" + \
            pretty_player_sets(names_list(player_set),
                               names_list(five_stack_set))
    else:
        new_message = "" + DEFAULT_MSG + "\n\n"\
            + "sadge/5"

    return new_message

# Returns pretty print formatted player sets


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

# Returns list of usernames(str) from input of a User collection


def names_list(users):
    result_list = []
    for user in users:
        result_list.append(user.name)
    return result_list


def bold(input):
    return "**" + input + "**"


def italics(input):
    return "*" + input + "*"


def help_message():
    return "ShootyBot help:" + "\n\n"\
        + "*$shooty* or *$st* -- Starts new Shooty session \n" \
        + "*$shooty status* or *$sts* -- Shows current Shooty session status \n"\
        + "*$shooty mention* or *$stm* -- Mentions all session members (5 stackers included)\n"\
        + "*$shooty clear* or *$stc* -- Clears current Shooty session"


bot.run(BOT_TOKEN)
