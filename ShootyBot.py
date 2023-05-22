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
from ShootyContext import *
from discord.ext import commands
import copy

logging.basicConfig(level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)

intents = discord.Intents.all()
intents.members = True

bot = commands.Bot(command_prefix=['$'], intents=intents)

shooty_context_dict = dict() # stores <channel, shooty_context> map
shooty_context_backup_dict = dict() # used in shooty restore to undo deletes
global timer


@bot.event
async def on_ready():
    logging.info('We have logged in as {0.user}'.format(bot))


@bot.event
async def on_message(message):
    global party_max_size
    
    await bot.process_commands(message)

    channel_id = message.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    # ensure bot only adds reaction emojis to messages by itself and containing the default message
    if message.author == bot.user and message.content.startswith(DEFAULT_MSG):
        shooty_context.current_st_message_id = message.id
        await add_react_options(message)


@bot.hybrid_command(name='shooty', with_app_command=True)
async def cmd_start_session(ctx):
    logging.info("Starting new shooty session")

    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)
    
    backup_user_sets(channel_id, shooty_context)

    shooty_context.reset_users()

    response_string = get_ping_shooty_message(shooty_context.role_code)
    await ctx.send(response_string)


def backup_user_sets(channel_id, old_shooty_context: ShootyContext):
    #backup in case of undo needed
    logging.info("trying backup")
    backup_shooty_context = ShootyContext(channel_id)
    backup_shooty_context.bot_ready_user_set = set(old_shooty_context.bot_ready_user_set)
    backup_shooty_context.bot_fullstack_user_set = set(old_shooty_context.bot_fullstack_user_set)
    backup_shooty_context.bot_soloq_user_set = set(old_shooty_context.bot_soloq_user_set)

    shooty_context_backup_dict[channel_id] = backup_shooty_context
    
@bot.hybrid_command(name='shootystatus')
async def cmd_session_status(ctx):
    logging.info("Printing Status")

    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)
    await ctx.reply(party_status_message(ctx.channel, shooty_context))


@bot.hybrid_command(name='shootymention')
async def cmd_mention_session(ctx):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    if not shooty_context.bot_soloq_user_set and not shooty_context.bot_fullstack_user_set:
        await ctx.send("No shooty boys to mention.")
        return

    mention_message = ''
    for user in shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set):
        if not user.bot:
            mention_message += user.mention + " "

    await ctx.send(mention_message)


@bot.hybrid_command(name='shootykick')
async def cmd_kick_user(ctx, args):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    potential_user_names_list = args
    kicked_usernames_list = shooty_context.remove_user_from_everything(
        potential_user_names_list)

    await ctx.reply(get_kicked_user_message(ctx.channel, kicked_usernames_list))


#TODO: fix this with shooty_context
@bot.hybrid_command(name='shootysize')
async def cmd_set_session_size(ctx, arg):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    if arg.isdigit():
        logging.info("Changing size to: " + arg)
        new_party_max_size = int(arg)
        shooty_context.set_party_max_size(new_party_max_size)

    await ctx.reply(get_max_party_size_message(new_party_max_size))


@bot.hybrid_command(name='shootyclear')
async def cmd_clear_session(ctx):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    #backup in case of undo needed
    backup_user_sets(channel_id, shooty_context)

    logging.info("Clearing user sets: " +
                 str(to_names_list(shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set))))
    shooty_context.reset_users()
    await ctx.send("Cleared shooty session.")

@bot.hybrid_command(name='shootyrestore')
async def cmd_restore(ctx):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    #restore backup
    shooty_context = shooty_context_backup_dict[channel_id]
    shooty_context_dict[channel_id] = shooty_context

    logging.info("Restoring shooty_context: " +
            str(to_names_list(shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set))))

    await ctx.channel.send("Restoring shooty session to before it was cleared.")
    await ctx.reply(party_status_message(ctx.channel, shooty_context))

@bot.hybrid_command(name='shootyhelp')
async def cmd_show_help(ctx):
    await send_help_message(ctx.channel)


@bot.hybrid_command(name='shootytime')
async def cmd_scheduled_session(ctx, input_time):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

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
        elif seconds_to_wait > 14400:  # 4 hrs
            await ctx.send("Shooty session can only be scheduled up to 4 hrs in advance.")
            return

        message = await ctx.send(f"Shooty at {scheduled_time.strftime('%I:%M %p')}?")
        await cmd_start_session(ctx)
        await asyncio.sleep(seconds_to_wait)
        # global timer
        # timer = threading.Timer(seconds_to_wait, send_party_status_message(ctx.channel))
        # timer.start()
        await ctx.send(f"Shooty time now! - {scheduled_time.strftime('%I:%M %p')}")
        await ctx.reply(party_status_message(ctx.channel, shooty_context))
    except ValueError:
        await ctx.send("Must be a valid time. Try format HH:MM")

#This function doesn't work yet
async def cmd_cancel_scheduled_session(ctx):

   # timer.cancel()
    await ctx.send(f"Canceled scheduled session - {scheduled_time.strftime('%H:%M %p')}")

async def cmd_dm_party_members(ctx):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    await shooty_context.dm_all_users_except_caller(None)

@bot.hybrid_command(name="shootysetrole")
async def cmd_set_role_code(ctx, role_code):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    shooty_context.role_code = role_code

    #save the channel_data to json locally
    shooty_context.set_channel_data(role_code=shooty_context.role_code, game_name=shooty_context.game_name, channel=channel_id)

    await ctx.send(f"Set this channel's role code for pings to {role_code}")

    
@bot.hybrid_command(name="shootylfg")
async def cmd_lfg(ctx):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    if shooty_context.game_name is None:
        await ctx.send(f"Set this channel's game name to see other queues with the same name ```$stsg <game name>```")
        return
    
    lobby_members_str = ""
    context:ShootyContext
    for context in shooty_context_dict.values():
        if context.game_name == shooty_context.game_name:
            lobby_members_str += f"{context.get_user_list_string_with_hashtag()}\n"

    await ctx.send(f"Cross channel users queued for {shooty_context.game_name}:\n{lobby_members_str}")

@bot.hybrid_command(name="shootybeacon")
async def cmd_beacon(ctx):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)    \

    if shooty_context.game_name is None:
        await ctx.send(f"Set this channel's game name to see other queues with the same name ```$stsg <game name>```")
        return

    context:ShootyContext
    channels_pinged_str = ""
    for context in shooty_context_dict.values():
        if context.game_name == shooty_context.game_name and context.channel is not shooty_context.channel:
            await context.channel.send(f"{context.role_code}\nBeacon from Server: *{shooty_context.channel.guild.name}*\n Channel: *{shooty_context.channel.name}*")
            channels_pinged_str += f"Server: *{context.channel.guild.name}*, Channel: *{context.channel.name}*\n"
        
    await ctx.send(f"Sent beacon ping to {channels_pinged_str}")
    
@bot.hybrid_command(name="shootysetgame")
async def cmd_set_game_name(ctx, game_name):
    channel_id = ctx.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    shooty_context.game_name = game_name.upper()
    shooty_context.channel = ctx.channel

    #save the channel_data to json locally
    shooty_context.set_channel_data(role_code=shooty_context.role_code, game_name=shooty_context.game_name, channel=channel_id)

    await ctx.send(f"Set this channel's game for LFG to {shooty_context.game_name}")

@bot.event
async def on_command_error(ctx, error):
    if ctx.message.content.startswith("$shooty") or ctx.message.content.startswith("$st") and isinstance(error, discord.ext.commands.errors.CommandNotFound):
        await ctx.send("Command not found. Use *$shootyhelp* for list of commands.")


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot or reaction.message.author != bot.user:
        return

    channel_id = reaction.message.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    if reaction.message.id is not shooty_context.current_st_message_id:
        logging.info(
            "Ignore react since it is not on the latest shootyBot message")
        return

    # handle main group of players
    if reaction.emoji == '\N{THUMBS UP SIGN}':
        # case: user was in the full stack only group and wanted to join the regular group
        # remove them from full stack group and put them in the regular group instead
        shooty_context.add_soloq_user(user)
        logging.info("stack:" + str(to_names_list(shooty_context.bot_soloq_user_set)))

        new_message = party_status_message(True, shooty_context)
        await reaction.message.edit(content=new_message)

    # handle full stack only players
    elif reaction.emoji == '5️⃣':
        if not shooty_context.is_soloq_user(user):
            shooty_context.add_fullstack_user(user)
            logging.info("fullstack:" +
                         str(to_names_list(shooty_context.bot_fullstack_user_set)))

        new_message = party_status_message(True, shooty_context)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        shooty_context.bot_ready_user_set.add(user)
        logging.info("ready_set:" + str(to_names_list(shooty_context.bot_ready_user_set)))

        new_message = party_status_message(True, shooty_context)

        await reaction.message.edit(content=new_message)


@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot or reaction.message.author != bot.user:
        return

    channel_id = reaction.message.channel.id
    shooty_context = get_shooty_context_from_channel_id(channel_id, shooty_context_dict)

    if reaction.message.id is not shooty_context.current_st_message_id:
        logging.info(
            "Ignore react since it is not on the latest shootyBot message")
        return

    # handle main group of players
    if reaction.emoji == '\N{THUMBS UP SIGN}' and shooty_context.is_soloq_user(user):
        shooty_context.remove_soloq_user(user)

        logging.info("Removed [" + user.name + "] from stack.")
        logging.info("stack:" + str(to_names_list(shooty_context.bot_soloq_user_set)))

        new_message = party_status_message(True, shooty_context)

        await reaction.message.edit(content=new_message)

    # handle full stack only players
    elif reaction.emoji == '5️⃣' and user in shooty_context.bot_fullstack_user_set:
        shooty_context.remove_fullstack_user(user)
        logging.info("Removed [" + user.name + "] from full stack.")
        logging.info("fullstack:" + str(to_names_list(shooty_context.bot_fullstack_user_set)))

        new_message = party_status_message(True, shooty_context)

        await reaction.message.edit(content=new_message)

    elif reaction.emoji == '✅':
        shooty_context.bot_ready_user_set.remove(user)
        logging.info("ready_set:" + str(to_names_list(shooty_context.bot_ready_user_set)))

        new_message = party_status_message(True, shooty_context)

        await reaction.message.edit(content=new_message)

@bot.command(name='shootysync')
async def sync(ctx) -> None:
        synced = await ctx.bot.tree.sync()
        await ctx.send(
            f"Synced {len(synced)} commands to the current guild."
        )
        return

# Logger helper


def to_names_list(user_set):
    result_list = []
    for user in user_set:
        result_list.append(user.name)
    return result_list


def get_shooty_context_from_channel_id(channel_id, shooty_context_dict: dict[str, ShootyContext]) -> ShootyContext:
    logging.info(f"channel_id: {channel_id}")

    if channel_id not in shooty_context_dict:
        #first try loading from json file
        shooty_context_dict[channel_id] = ShootyContext(channel_id)

        shooty_context_dict[channel_id].load_channel_data

    return shooty_context_dict[channel_id]

bot.run(BOT_TOKEN)
