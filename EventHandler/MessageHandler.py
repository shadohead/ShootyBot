from DiscordConfig import *
from UserTracker import *
from EventHandler.MessageFormatter import *

DEFAULT_MSG = "‎"  # Invisible character magic (this is terrible lol)


async def add_react_options(message):
    await message.add_reaction('\N{THUMBS UP SIGN}')
    await message.add_reaction('5️⃣')
    await message.add_reaction('✅')


async def ping_shooty(channel):
    await channel.send(DEFAULT_MSG+SHOOTY_ROLE_CODE)


async def send_party_status_message(channel):
    await channel.send(party_status_message(True))


async def send_kicked_user_message(channel, kicked_usernames_list):
    await channel.send("Kicked: " + str(kicked_usernames_list))


async def send_max_party_size_message(channel):
    await channel.send("Current party size: " + str(get_party_max_size()))


async def send_help_message(channel):
    await channel.send("DaboysBot help:" + "\n\n"
                       + "*$daboys* or *$db* -- Starts new daboys session \n"
                       + "*$daboysstatus* or *$dbs* -- Shows current daboys session status \n"
                       + "*$daboysmention* or *dbm* -- Mentions all session members (full stackers included)\n"
                       + "*$daboyskick user1 ...* or *$dtk user1 ...* -- Kick the shooter(s) from session\n"
                       + "*$daboyssize N*  -- Set the max party size\n"
                       + "*$daboysclear* or *$stc* -- Clears current daboys session\n"
                       + "*$daboystime HH:MM(AM/PM)* or *$stt HH:MM(AM/PM)* -- Schedules a new daboys session for the input time\n"
                       + "*$daboysdm* or *$stdm* -- DMs all other users who are in the daboys session\n")


async def mention_reactors(channel):
    if not bot_soloq_user_set and not bot_fullstack_user_set:
        await channel.send("No boys to mention.")
        return

    mention_message = ''
    for user in bot_soloq_user_set.union(bot_fullstack_user_set):
        if not user.bot:
            mention_message += user.mention + " "

    await channel.send(mention_message)

# String formatted with status of the shooty crew


def party_status_message(isPing):
    num_soloq_users = get_soloq_user_count()
    num_fullstack_users = get_fullstack_user_count()

    if isPing:
        msg = DEFAULT_MSG + SHOOTY_ROLE_CODE
    else:
        msg = DEFAULT_MSG

    if num_soloq_users + num_fullstack_users >= get_party_max_size():
        new_message = msg + "\n\n"\
            + bold(str(num_soloq_users + num_fullstack_users) + "/" + str(get_party_max_size()))\
            + "\n" + \
            get_user_list_string()
    elif num_soloq_users > 0 and num_fullstack_users > 0:
        new_message = msg + "\n\n"\
            + bold(str(num_soloq_users)) + "(" + str(num_soloq_users + num_fullstack_users) + ")" + bold("/" + str(get_party_max_size()))\
            + "\n" + \
            get_user_list_string()

    elif num_soloq_users > 0:
        new_message = msg + "\n\n"\
            + bold(str(num_soloq_users) + "/" + str(get_party_max_size()))\
            + "\n" + \
            get_user_list_string()

    elif num_fullstack_users > 0:
        new_message = msg + "\n\n"\
            + "(" + str(num_fullstack_users) + ")" + bold("/" + str(get_party_max_size()))\
            + "\n" + \
            get_user_list_string()
    else:
        new_message = "" + msg + "\n\n"\
            + "sadge/" + str(get_party_max_size())

    return new_message
