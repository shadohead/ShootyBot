
import discord
import pprint
import logging

from discord.ext import commands

logging.basicConfig(level=logging.INFO)
pp = pprint.PrettyPrinter(indent=4)

bot_token = '' #set bot token here to run

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!!', intents=intents)

default_msg = "<@&773770148070424657>" #shooty role code
users_who_reacted = set()

@bot.event
async def on_ready():
    print('We have logged in as {0.user}'.format(bot))


@bot.event
async def on_message(message):
    if message.author == bot.user:
        await message.add_reaction('\N{THUMBS UP SIGN}')

    if message.content.startswith('$shooty'):
        users_who_reacted.clear

        #shooty_role = discord.utils.get(message.channel.guild.roles, name="shooty shooty")
        await message.channel.send(default_msg)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot or reaction.message.author != bot.user:
        return
    
    if reaction.emoji == '\N{THUMBS UP SIGN}':
        users_who_reacted.add(user.name)
        print(users_who_reacted)

        if users_who_reacted:
            new_message = default_msg + "\n\n"\
            + str(len(users_who_reacted)) + "/5"\
            + "\n" + pprint.pformat(users_who_reacted)
        else:
            new_message = "" + default_msg + "\n\n"\
            + "sadge/5" 

        await reaction.message.edit(content=new_message)

@bot.event
async def on_reaction_remove(reaction, user):
    print("detected remove")
    if user.bot or reaction.message.author != bot.user:
        return
    
    if reaction.emoji == '\N{THUMBS UP SIGN}':
        users_who_reacted.remove(user.name)
        print(users_who_reacted)
        if users_who_reacted:
            new_message = "" + default_msg + "\n\n"\
            + str(len(users_who_reacted)) + "/5"\
            + "\n" + pprint.pformat(users_who_reacted)
        else:
            new_message = "" + default_msg + "\n\n"\
            + "sadge/5" 

        await reaction.message.edit(content=new_message)

bot.run(bot_token)