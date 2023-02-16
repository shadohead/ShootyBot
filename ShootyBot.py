from datetime import date, datetime
import discord
import pprint
import logging
import pytz  # pip install pytz
import threading
import asyncio
from dateutil import parser  # pip install python-dateutil
from discord import player
from DiscordConfig import *
from EventHandler.MessageHandler import *
from UserTracker import *
from UserSets import *
from discord.ext import commands

logging.basicConfig(level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)

intents = discord.Intents.all()
intents.members = True

bot = commands.Bot(command_prefix=['$'], intents=intents)

latest_bot_message_time = datetime.now()
latest_shooty_session_time = 0

user_sets = UserSets()
global timer


@bot.event
async def on_ready():
    logging.info('We have logged in as {0.user}'.format(bot))

@bot.event
async def on_message(message):
    global latest_bot_message_time
    global party_max_size
    
    await bot.process_commands(message)

    # ensure bot only adds reaction emojis to messages by itself and containing the default message
    if message.author == bot.user and message.content.startswith(DEFAULT_MSG):
        latest_bot_message_time = message.created_at
        await add_react_options(message)


@bot.command(name='shooty', aliases=['st'])
async def cmd_start_session(ctx):
    logging.info("Starting new shooty session")
    latest_shooty_session_time = datetime.now()
    user_sets.reset_users()
    await ping_shooty(ctx.channel)


@bot.command(name='shootystatus', aliases=['sts'])
async def cmd_session_status(ctx):
    logging.info("Printing Status")
    await send_party_status_message(ctx.channel, user_sets)


@bot.command(name='shootymention', aliases=['stm'])
async def cmd_mention_session(ctx):
    await mention_reactors(ctx.channel, user_sets)


@bot.command(name='shootykick', aliases=['stk'])
async def cmd_kick_user(ctx, *args):
    potential_user_names_list = args
    kicked_usernames_list = user_sets.remove_user_from_everything(
        potential_user_names_list)

    await send_kicked_user_message(ctx.channel, kicked_usernames_list)


@bot.command(name='shootysize')
async def cmd_set_session_size(ctx, arg):
    if arg.isdigit():
        logging.info("Changing size to: " + arg)
        new_party_max_size = int(arg)
        set_party_max_size(new_party_max_size)

    await send_max_party_size_message(ctx.channel)


@bot.command(name='shootyclear', aliases=['stc'])
async def cmd_clear_session(ctx):
    logging.info("Clearing user sets: " +
                 str(to_names_list(user_sets.bot_soloq_user_set.union(user_sets.bot_fullstack_user_set))))
    user_sets.reset_users()
    await ctx.channel.send("Cleared shooty session.")


@bot.command(name='shootyhelp', aliases=['sth'])
async def cmd_show_help(ctx, *args):
    await send_help_message(ctx.channel)


@bot.command(name='shootytime', aliases=['stt'])
async def cmd_scheduled_session(ctx, input_time):
    # parse input time
    # await difference of scheduled and current time
    # conditions: input must be greater than current

    try:
        scheduled_time = parser.parse(input_time)
        # create both timezone objects
        old_timezone = pytz.timezone("US/Pacific")
        new_timezone = pytz.timezone("UTC")

        # two-step process to convert input time to UTC
        localized_timestamp = old_timezone.localize(scheduled_time)
        utc_scheduled_time = localized_timestamp.astimezone(new_timezone)

        seconds_to_wait = (utc_scheduled_time -
                           datetime.now(pytz.UTC)).total_seconds()

        if seconds_to_wait < 0:
            await ctx.send("Shooty session cannot be scheduled in the past.")
            return
        elif seconds_to_wait > 14400:  # 2 hrs
            await ctx.send("Shooty session can only be scheduled up to 4 hrs in advance.")
            return

        message = await ctx.send(f"Shooty at {scheduled_time.strftime('%I:%M %p')}?")
        await cmd_start_session(ctx)
        await asyncio.sleep(seconds_to_wait)
        # global timer
        # timer = threading.Timer(seconds_to_wait, send_party_status_message(ctx.channel))
        # timer.start()
        await ctx.send(f"Shooty time now! - {scheduled_time.strftime('%I:%M %p')}")
        await send_party_status_message(ctx.channel, user_sets)
    except ValueError:
        await ctx.send("Must be a valid time. Try format HH:MM")

#This function doesn't work yet
@bot.command(name='shootytimecancel', aliases=['sttc'])
async def cmd_cancel_scheduled_session(ctx):

   # timer.cancel()
    await ctx.send(f"Canceled scheduled session - {scheduled_time.strftime('%H:%M %p')}")

@bot.command(name='shootydm', aliases=['stdm'])
async def cmd_dm_party_members(ctx):
    await user_sets.dm_all_users_except_caller(ctx.author)

@bot.event
async def on_command_error(ctx, error):
    if ctx.message.content.startswith("$shooty") or ctx.message.content.startswith("$st") and isinstance(error, discord.ext.commands.errors.CommandNotFound):
        await ctx.send("Command not found. Use *$shootyhelp* for list of commands.")


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
        user_sets.add_soloq_user(user)
        logging.info("stack:" + str(to_names_list(user_sets.bot_soloq_user_set)))

        new_message = party_status_message(True, user_sets)
        await reaction.message.edit(content=new_message)

    # handle full stack only players
    elif reaction.emoji == '5️⃣':
        if not user_sets.is_soloq_user(user):
            user_sets.add_fullstack_user(user)
            logging.info("fullstack:" +
                         str(to_names_list(user_sets.bot_fullstack_user_set)))

        new_message = party_status_message(True, user_sets)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        user_sets.bot_ready_user_set.add(user)
        logging.info("ready_set:" + str(to_names_list(user_sets.bot_ready_user_set)))

        new_message = party_status_message(True, user_sets)

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
    if reaction.emoji == '\N{THUMBS UP SIGN}' and user_sets.is_soloq_user(user):
        user_sets.remove_soloq_user(user)

        logging.info("Removed [" + user.name + "] from stack.")
        logging.info("stack:" + str(to_names_list(user_sets.bot_soloq_user_set)))

        new_message = party_status_message(True, user_sets)

        await reaction.message.edit(content=new_message)

    # handle full stack only players
    elif reaction.emoji == '5️⃣' and user in user_sets.bot_fullstack_user_set:
        user_sets.remove_fullstack_user(user)
        logging.info("Removed [" + user.name + "] from full stack.")
        logging.info("fullstack:" + str(to_names_list(user_sets.bot_fullstack_user_set)))

        new_message = party_status_message(True, user_sets)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        user_sets.bot_ready_user_set.remove(user)
        logging.info("ready_set:" + str(to_names_list(user_sets.bot_ready_user_set)))

        new_message = party_status_message(True, user_sets)

        await reaction.message.edit(content=new_message)

# Logger helper


def to_names_list(user_set):
    result_list = []
    for user in user_set:
        result_list.append(user.name)
    return result_list


bot.run(BOT_TOKEN)
