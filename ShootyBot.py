from datetime import date, datetime
import discord
import pprint
import logging

from discord.ext import commands

logging.basicConfig(level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)

# set bot token here to run
BOT_TOKEN = ''
DEFAULT_MSG = "<@&773770148070424657>"  # shooty role code

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!!', intents=intents)

users_who_reacted = set()
latest_bot_message_time = datetime.now()


@bot.event
async def on_ready():
    logging.info('We have logged in as {0.user}'.format(bot))


@bot.event
async def on_message(message):
    global latest_bot_message_time
    if message.author == bot.user:
        latest_bot_message_time = message.created_at
        await message.add_reaction('\N{THUMBS UP SIGN}')

    if message.content.startswith('$shooty'):
        users_who_reacted.clear

        #shooty_role = discord.utils.get(message.channel.guild.roles, name="shooty shooty")
        await message.channel.send(DEFAULT_MSG)


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot or reaction.message.author != bot.user:
        return

    if reaction.message.created_at < latest_bot_message_time:
        logging.info(
            "Ignore react since it is not on the latest shootyBot message")
        return

    if reaction.emoji == '\N{THUMBS UP SIGN}':
        users_who_reacted.add(user.name)
        logging.info(users_who_reacted)

        if users_who_reacted:
            new_message = DEFAULT_MSG + "\n\n"\
                + str(len(users_who_reacted)) + "/5"\
                + "\n" + pp.pformat(users_who_reacted)
        else:
            new_message = "" + DEFAULT_MSG + "\n\n"\
                + "sadge/5"

        await reaction.message.edit(content=new_message)


@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot or reaction.message.author != bot.user or user.name not in users_who_reacted:
        return

    if reaction.message.created_at < latest_bot_message_time:
        logging.info(
            "Ignore react since it is not on the latest shootyBot message")
        return

    if reaction.emoji == '\N{THUMBS UP SIGN}':
        users_who_reacted.remove(user.name)

        logging.info("Removed [" + user.name + "] from shooty session.")
        logging.info(users_who_reacted)

        if users_who_reacted:
            new_message = "" + DEFAULT_MSG + "\n\n"\
                + str(len(users_who_reacted)) + "/5"\
                + "\n" + pp.pformat(users_who_reacted)
        else:
            new_message = "" + DEFAULT_MSG + "\n\n"\
                + "sadge/5"

        await reaction.message.edit(content=new_message)

bot.run(BOT_TOKEN)
