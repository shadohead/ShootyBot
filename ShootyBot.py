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
DEFAULT_MSG = "‎"  # Invisible character magic (this is terrible lol)
SHOOTY_ROLE_CODE = "<@&773770148070424657>"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!!', intents=intents)

user_set = set()  # set with all the users in the shooty crew
user_5_set = set()  # set with all the 5 stack only users in the shooty crew
ready_set = set()  # set with all players who said they're ready to play right now
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
        await message.add_reaction('✅')

    # default mode: create new session
    if message.content == ('$shooty') or message.content == ('$st'):
        logging.info("Starting new shooty session")
        user_set.clear()
        user_5_set.clear()

        await message.channel.send(DEFAULT_MSG+SHOOTY_ROLE_CODE)

    # display status
    elif message.content == ('$shooty status') or message.content == ('$sts'):
        logging.info("Printing Status")
        await message.channel.send(party_status_message(user_set, user_5_set, True))

    # clear the user sets
    elif message.content == ('$shooty clear') or message.content == ('$stc'):
        logging.info("Clearing user sets: " +
                     str(to_names_list(user_set.union(user_5_set))))
        user_set.clear()
        user_5_set.clear()

        await message.channel.send("Cleared shooty session.")

    # mention all reactors
    elif message.content == ('$shooty mention') or message.content == ('$stm'):
        await mention_reactors(message)

    # remove the person from both groups
    elif message.content.startswith('$shooty kick'):
        split_message = message.content.split()
        kick_users_names = split_message[2:]
        actually_kicked_usernames = []
        for username in kick_users_names:
            for user in user_set.copy():
                if user.name.startswith(username):
                    user_set.remove(user)
                    actually_kicked_usernames.append(user.name)

            for user in user_5_set.copy():
                if user.name.startswith(username):
                    user_5_set.remove(user)
                    actually_kicked_usernames.append(user.name)

        await message.channel.send("Kicked: " + str(actually_kicked_usernames))

    elif message.content.startswith('$stk'):
        split_message = message.content.split()
        kick_users_names = split_message[1:]
        actually_kicked_usernames = []

        for username in kick_users_names:
            for user in user_set.copy():
                if user.name.startswith(username):
                    user_set.remove(user)
                    actually_kicked_usernames.append(user.name)

            for user in user_5_set.copy():
                if user.name.startswith(username):
                    user_5_set.remove(user)
                    actually_kicked_usernames.append(user.name)

        await message.channel.send("Kicked: " + str(actually_kicked_usernames))

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
        logging.info("stack:" + str(to_names_list(user_set)))

        new_message = party_status_message(
            user_set, user_5_set, True)

        await reaction.message.edit(content=new_message)

    # handle 5 stack only players
    elif reaction.emoji == '5️⃣':
        if user not in user_set:
            user_5_set.add(user)
            logging.info("5stack:" + str(to_names_list(user_5_set)))

        new_message = party_status_message(
            user_set, user_5_set, True)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        ready_set.add(user)
        logging.info("ready_set:" + str(to_names_list(ready_set)))

        new_message = party_status_message(
            user_set, user_5_set, True)

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
        logging.info("stack:" + str(to_names_list(user_set)))

        # case: user removed themselves from the regular group, but still has a react for the 5 stack
        # check if user has a 5 stack emoji react, if so add them back to that set
        if user in await reaction.message.reactions[1].users().flatten():
            user_5_set.add(user)
            logging.info("5stack:" + str(to_names_list(user_set)))

        new_message = party_status_message(
            user_set, user_5_set, True)

        await reaction.message.edit(content=new_message)

    # handle 5 stack only players
    elif reaction.emoji == '5️⃣' and user in user_5_set:
        user_5_set.remove(user)
        logging.info("Removed [" + user.name + "] from 5 stack.")
        logging.info("5stack:" + str(to_names_list(user_5_set)))

        new_message = party_status_message(
            user_set, user_5_set, True)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        ready_set.remove(user)
        logging.info("ready_set:" + str(to_names_list(ready_set)))

        new_message = party_status_message(
            user_set, user_5_set, True)

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
def party_status_message(player_set, five_stack_set, isPing):
    num_players = len(player_set)
    num_5players = len(five_stack_set)

    if isPing:
        msg = DEFAULT_MSG + SHOOTY_ROLE_CODE
    else:
        msg = DEFAULT_MSG

    if num_players+num_5players >= 5:
        new_message = msg + "\n\n"\
            + bold(str(num_players+num_5players) + "/5")\
            + "\n" + \
            pretty_player_sets(player_set, five_stack_set)
    elif player_set and five_stack_set:
        new_message = msg + "\n\n"\
            + bold(str(num_players)) + "(" + str(num_players+num_5players) + ")" + bold("/5")\
            + "\n" + \
            pretty_player_sets(player_set, five_stack_set)

    elif player_set:
        new_message = msg + "\n\n"\
            + bold(str(num_players) + "/5")\
            + "\n" + \
            pretty_player_sets(player_set, five_stack_set)

    elif five_stack_set:
        new_message = msg + "\n\n"\
            + "(" + str(num_5players) + ")" + bold("/5")\
            + "\n" + \
            pretty_player_sets(player_set, five_stack_set)
    else:
        new_message = "" + msg + "\n\n"\
            + "sadge/5"

    return new_message

# Returns pretty print formatted player sets with input names list


def pretty_player_sets(player_set, five_stack_set):
    result_string = ''

    for index, player_user in enumerate(player_set):
        result_string += bold_ready_user(player_user)

        # if it's not the last player, add a comma
        if index < len(player_set) + len(five_stack_set) - 1:
            result_string += ", "

    for index, player_user in enumerate(five_stack_set):
        result_string += italics(bold_ready_user(player_user))

        # if it's not the last player, add a comma
        if index < len(five_stack_set) - 1:
            result_string += ", "

    return result_string

# Returns list of usernames(str) from input of a User collection


def to_names_list(users):
    result_list = []
    for user in users:
        result_list.append(user.name)
    return result_list


def bold(input):
    return "**" + input + "**"

# Returns bold username if the user is ready


def bold_ready_user(input_user):
    if input_user in ready_set:
        return "**" + input_user.name + "**"
    else:
        return input_user.name


def italics(input):
    return "*" + input + "*"


def help_message():
    return "ShootyBot help:" + "\n\n"\
        + "*$shooty* or *$st* -- Starts new Shooty session \n" \
        + "*$shooty status* or *$sts* -- Shows current Shooty session status \n"\
        + "*$shooty mention* or *$stm* -- Mentions all session members (5 stackers included)\n"\
        + "*$shooty kick* or *$stk* -- Kick the shooter(s) from session\n"\
        + "*$shooty clear* or *$stc* -- Clears current Shooty session"


bot.run(BOT_TOKEN)
