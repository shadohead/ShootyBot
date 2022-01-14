from datetime import date, datetime
import discord
import pprint
import logging
from discord import player

from discord.ext import commands

logging.basicConfig(level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)

# set bot token here to run
BOT_TOKEN = 'OTMxMDgxNjUzNjE3NTc4MDA3.Yd_PXA.mFNGsYewecvGii4fm0A8BwkFoaI'
DEFAULT_MSG = "‎"  # Invisible character magic (this is terrible lol)
SHOOTY_ROLE_CODE = "<@&773770148070424657>"
DEFAULT_PARTY_SIZE = 5

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!!', intents=intents)

bot_soloq_user_set = set()  # set with all the users in the shooty crew
bot_fullstack_user_set = set()  # set with all the full stack only users in the shooty crew
bot_ready_user_set = set()  # set with all players who said they're ready to play right now
latest_bot_message_time = datetime.now()
party_max_size = DEFAULT_PARTY_SIZE

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
        await message.add_reaction('\N{THUMBS UP SIGN}')
        await message.add_reaction('5️⃣')
        await message.add_reaction('✅')

    # default mode: create new session
    if message.content == ('$shooty') or message.content == ('$st'):
        logging.info("Starting new shooty session")
        bot_soloq_user_set.clear()
        bot_fullstack_user_set.clear()
        bot_ready_user_set.clear()

        await message.channel.send(DEFAULT_MSG+SHOOTY_ROLE_CODE)

    # display status
    elif message.content == ('$shooty status') or message.content == ('$sts'):
        logging.info("Printing Status")
        await message.channel.send(party_status_message(bot_soloq_user_set, bot_fullstack_user_set, True))

    # clear the user sets
    elif message.content == ('$shooty clear') or message.content == ('$stc'):
        logging.info("Clearing user sets: " +
                     str(to_names_list(bot_soloq_user_set.union(bot_fullstack_user_set))))
        bot_soloq_user_set.clear()
        bot_fullstack_user_set.clear()
        bot_ready_user_set.clear()

        await message.channel.send("Cleared shooty session.")

    # mention all reactors
    elif message.content == ('$shooty mention') or message.content == ('$stm'):
        await mention_reactors(message)

    # remove the person from both groups
    elif message.content.startswith('$shooty kick'):
        split_message = message.content.split()
        user_names_list = split_message[2:]
        kicked_usernames_list = []
        for username in user_names_list:
            for user in bot_soloq_user_set.copy():
                if user.name.startswith(username):
                    bot_soloq_user_set.remove(user)
                    kicked_usernames_list.append(user.name)

            for user in bot_fullstack_user_set.copy():
                if user.name.startswith(username):
                    bot_fullstack_user_set.remove(user)
                    kicked_usernames_list.append(user.name)

        await message.channel.send("Kicked: " + str(kicked_usernames_list))

    elif message.content.startswith('$stk'):
        split_message = message.content.split()
        user_names_list = split_message[1:]
        kicked_usernames_list = []

        for username in user_names_list:
            for user in bot_soloq_user_set.copy():
                if user.name.startswith(username):
                    bot_soloq_user_set.remove(user)
                    kicked_usernames_list.append(user.name)

            for user in bot_fullstack_user_set.copy():
                if user.name.startswith(username):
                    bot_fullstack_user_set.remove(user)
                    kicked_usernames_list.append(user.name)

        await message.channel.send("Kicked: " + str(kicked_usernames_list))
    
    elif message.content.startswith('$shooty size'):
        split_message = message.content.split()

        if len(split_message) >= 3 and split_message[2].isdigit():
            new_party_size = split_message[2]
            party_max_size = int(new_party_size)
        else:
            await message.channel.send("Current party size: " + str(party_max_size))

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
        # case: user was in the full stack only group and wanted to join the regular group
        # remove them from full stack group and put them in the regular group instead
        if user in bot_fullstack_user_set:
            bot_fullstack_user_set.remove(user)

        bot_soloq_user_set.add(user)
        logging.info("stack:" + str(to_names_list(bot_soloq_user_set)))

        new_message = party_status_message(
            bot_soloq_user_set, bot_fullstack_user_set, True)

        await reaction.message.edit(content=new_message)

    # handle full stack only players
    elif reaction.emoji == '5️⃣':
        if user not in bot_soloq_user_set:
            bot_fullstack_user_set.add(user)
            logging.info("fullstack:" + str(to_names_list(bot_fullstack_user_set)))

        new_message = party_status_message(
            bot_soloq_user_set, bot_fullstack_user_set, True)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        bot_ready_user_set.add(user)
        logging.info("ready_set:" + str(to_names_list(bot_ready_user_set)))

        new_message = party_status_message(
            bot_soloq_user_set, bot_fullstack_user_set, True)

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
    if reaction.emoji == '\N{THUMBS UP SIGN}' and user in bot_soloq_user_set:
        bot_soloq_user_set.remove(user)

        logging.info("Removed [" + user.name + "] from stack.")
        logging.info("stack:" + str(to_names_list(bot_soloq_user_set)))

        # case: user removed themselves from the regular group, but still has a react for the full stack
        # check if user has a full stack emoji react, if so add them back to that set
        if user in await reaction.message.reactions[1].users().flatten():
            bot_fullstack_user_set.add(user)
            logging.info("fullstack:" + str(to_names_list(bot_soloq_user_set)))

        new_message = party_status_message(
            bot_soloq_user_set, bot_fullstack_user_set, True)

        await reaction.message.edit(content=new_message)

    # handle full stack only players
    elif reaction.emoji == '5️⃣' and user in bot_fullstack_user_set:
        bot_fullstack_user_set.remove(user)
        logging.info("Removed [" + user.name + "] from full stack.")
        logging.info("fullstack:" + str(to_names_list(bot_fullstack_user_set)))

        new_message = party_status_message(
            bot_soloq_user_set, bot_fullstack_user_set, True)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        bot_ready_user_set.remove(user)
        logging.info("ready_set:" + str(to_names_list(bot_ready_user_set)))

        new_message = party_status_message(
            bot_soloq_user_set, bot_fullstack_user_set, True)

        await reaction.message.edit(content=new_message)

# Sends message mentioning everyone in the shooty crew


async def mention_reactors(message):
    if not bot_soloq_user_set and not bot_fullstack_user_set:
        await message.channel.send("No shooty boys to mention.")
        return

    mention_message = ''
    for user in bot_soloq_user_set.union(bot_fullstack_user_set):
        if not user.bot:
            mention_message += user.mention + " "

    await message.channel.send(mention_message)


# String formatted with status of the shooty crew
def party_status_message(soloq_users_set, fullstack_users_set, isPing):
    num_soloq_players = len(soloq_users_set)
    num_fullstack_players = len(fullstack_users_set)

    if isPing:
        msg = DEFAULT_MSG + SHOOTY_ROLE_CODE
    else:
        msg = DEFAULT_MSG

    if num_soloq_players+num_fullstack_players >= party_max_size:
        new_message = msg + "\n\n"\
            + bold(str(num_soloq_players+num_fullstack_players) + "/" + str(party_max_size))\
            + "\n" + \
            pretty_player_sets(soloq_users_set, fullstack_users_set)
    elif soloq_users_set and fullstack_users_set:
        new_message = msg + "\n\n"\
            + bold(str(num_soloq_players)) + "(" + str(num_soloq_players+num_fullstack_players) + ")" + bold("/" + str(party_max_size))\
            + "\n" + \
            pretty_player_sets(soloq_users_set, fullstack_users_set)

    elif soloq_users_set:
        new_message = msg + "\n\n"\
            + bold(str(num_soloq_players) + "/" + str(party_max_size))\
            + "\n" + \
            pretty_player_sets(soloq_users_set, fullstack_users_set)

    elif fullstack_users_set:
        new_message = msg + "\n\n"\
            + "(" + str(num_fullstack_players) + ")" + bold("/" + str(party_max_size))\
            + "\n" + \
            pretty_player_sets(soloq_users_set, fullstack_users_set)
    else:
        new_message = "" + msg + "\n\n"\
            + "sadge/" + str(party_max_size)

    return new_message

# Returns pretty print formatted player sets with input names list


def pretty_player_sets(soloq_users_set, fullstack_users_set):
    result_string = ''

    for index, user in enumerate(soloq_users_set):
        result_string += bold_readied_user(user)

        # if it's not the last player, add a comma
        if index < len(soloq_users_set) + len(fullstack_users_set) - 1:
            result_string += ", "

    for index, user in enumerate(fullstack_users_set):
        result_string += italics(bold_readied_user(user))

        # if it's not the last player, add a comma
        if index < len(fullstack_users_set) - 1:
            result_string += ", "

    return result_string

# Returns list of usernames(str) from input of a User collection


def to_names_list(user_set):
    result_list = []
    for user in user_set:
        result_list.append(user.name)
    return result_list


def bold(input_str):
    return "**" + input_str + "**"

# Returns bold username if the user is ready


def bold_readied_user(user):
    if user in bot_ready_user_set:
        return "**" + user.name + "**"
    else:
        return user.name


def italics(input_str):
    return "*" + input_str + "*"


def help_message():
    return "ShootyBot help:" + "\n\n"\
        + "*$shooty* or *$st* -- Starts new Shooty session \n" \
        + "*$shooty status* or *$sts* -- Shows current Shooty session status \n"\
        + "*$shooty mention* or *$stm* -- Mentions all session members (full stackers included)\n"\
        + "*$shooty kick user1 ...* or *$stk user1 ...* -- Kick the shooter(s) from session\n"\
        + "*$shooty size N*  -- Set the max party size\n"\
        + "*$shooty clear* or *$stc* -- Clears current Shooty session"


bot.run(BOT_TOKEN)
