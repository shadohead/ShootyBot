from DiscordConfig import *
from UserTracker import *
from EventHandler.MessageFormatter import *
from ShootyContext import *

DEFAULT_MSG = "‎"  # Invisible character magic (this is terrible lol)


async def add_react_options(message):
    await message.add_reaction('\N{THUMBS UP SIGN}')
    await message.add_reaction('5️⃣')
    await message.add_reaction('✅')


async def ping_shooty(channel, role_code):
    if role_code is None:
        await channel.send("First set the role for the bot to ping with ```$stsr <Role>```")
    else:
        await channel.send(DEFAULT_MSG+role_code)


async def send_party_status_message(channel, user_sets: ShootyContext):
    await channel.send(party_status_message(True, user_sets))


async def send_kicked_user_message(channel, kicked_usernames_list):
    await channel.send("Kicked: " + str(kicked_usernames_list))


async def send_max_party_size_message(channel):
    await channel.send("Current party size: " + str(get_party_max_size()))


async def send_help_message(channel):
    await channel.send("ShootyBot help:" + "\n\n"
                       + "*$shooty* or *$st* -- Starts new Shooty session \n"
                       + "*$shootystatus* or *$sts* -- Shows current Shooty session status \n"
                       + "*$shootymention* or *$stm* -- Mentions all session members (full stackers included)\n"
                       + "*$shootykick user1 ...* or *$stk user1 ...* -- Kick the shooter(s) from session\n"
                       + "*$shootysize N*  -- Set the max party size\n"
                       + "*$shootyclear* or *$stc* -- Clears current Shooty session\n"
                       + "*$shootytime HH:MM(AM/PM)* or *$stt HH:MM(AM/PM)* -- Schedules a new Shooty session for the input time\n"
                       + "*$shootylfg* or *$stlfg* -- Shows all players queued for the current game across all channels\n"
                       + "*$shootybeacon* or *$stb* -- Ping every other channel associated with the current game\n"
                       + "*$shootysetgame* or *$stsg* -- Set the game for this channel needed for LFG features\n"
                       + "*$shootyrestore* or *$str* -- Restore a previous session in case of accidental delete\n")


async def mention_reactors(channel, user_sets: ShootyContext):
    if not user_sets.bot_soloq_user_set and not user_sets.bot_fullstack_user_set:
        await channel.send("No shooty boys to mention.")
        return

    mention_message = ''
    for user in user_sets.bot_soloq_user_set.union(user_sets.bot_fullstack_user_set):
        if not user.bot:
            mention_message += user.mention + " "

    await channel.send(mention_message)

# String formatted with status of the shooty crew


def party_status_message(is_ping, user_sets: ShootyContext):
    num_soloq_users = user_sets.get_soloq_user_count()
    num_fullstack_users = user_sets.get_fullstack_user_count()
    num_unique_users = user_sets.get_unique_user_count()

    all_users_set = user_sets.bot_soloq_user_set.union(user_sets.bot_fullstack_user_set)

    if is_ping:
        msg = DEFAULT_MSG + user_sets.role_code
    else:
        msg = DEFAULT_MSG

    if num_unique_users >= get_party_max_size():
        new_message = msg + "\n\n"\
            + bold(str(num_unique_users) + "/" + str(get_party_max_size())) + " <:jettpog:724145370023591937>"\
            + "\n" + \
            user_sets.get_user_list_string()
    elif num_soloq_users > 0 and num_unique_users > num_soloq_users:
        new_message = msg + "\n\n"\
            + bold(str(num_soloq_users)) + "(" + str(num_unique_users) + ")" + bold("/" + str(get_party_max_size()))\
            + "\n" + \
            user_sets.get_user_list_string()

    elif num_soloq_users > 0:
        new_message = msg + "\n\n"\
            + bold(str(num_soloq_users) + "/" + str(get_party_max_size()))\
            + "\n" + \
           user_sets.get_user_list_string()

    elif num_fullstack_users > 0:
        new_message = msg + "\n\n"\
            + "(" + str(num_fullstack_users) + ")" + bold("/" + str(get_party_max_size()))\
            + "\n" + \
            user_sets.get_user_list_string()
    else:
        new_message = "" + msg + "\n\n"\
            + "sadge/" + str(get_party_max_size()) + " <:viper:725612569716326422>"

    return new_message
