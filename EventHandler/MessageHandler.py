from DiscordConfig import *
from EventHandler.MessageFormatter import *
from ShootyContext import *

DEFAULT_MSG = "‎"  # Invisible character magic (this is terrible lol)


async def add_react_options(message):
    await message.add_reaction("\N{THUMBS UP SIGN}")
    await message.add_reaction("5️⃣")
    # await message.add_reaction('✅')
    await message.add_reaction("🔄")
    await message.add_reaction(":loudspeaker:")


def get_ping_shooty_message(role_code):
    if role_code is None:
        return "First set the role for the bot to ping with ```$stsr <Role>```"
    else:
        return f"{DEFAULT_MSG}{role_code}"


def get_kicked_user_message(kicked_usernames_list):
    return "Kicked: " + str(kicked_usernames_list)


def get_max_party_size_message(party_size):
    return f"Current party size: {party_size}"


def get_help_message():
    return "For command list and descriptions, type `/st` for primary and `/shooty` for secondary commands."


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

    if num_unique_users >= user_sets.get_party_max_size():
        new_message = (
            msg
            + "\n\n"
            + bold(str(num_unique_users) + "/" + str(user_sets.get_party_max_size()))
            + " <:jettpog:724145370023591937>"
            + "\n"
            + user_sets.get_user_list_string()
        )
    elif num_soloq_users > 0 and num_unique_users > num_soloq_users:
        new_message = (
            msg
            + "\n\n"
            + bold(str(num_soloq_users))
            + "("
            + str(num_unique_users)
            + ")"
            + bold("/" + str(user_sets.get_party_max_size()))
            + "\n"
            + user_sets.get_user_list_string()
        )

    elif num_soloq_users > 0:
        new_message = (
            msg
            + "\n\n"
            + bold(str(num_soloq_users) + "/" + str(user_sets.get_party_max_size()))
            + "\n"
            + user_sets.get_user_list_string()
        )

    elif num_fullstack_users > 0:
        new_message = (
            msg
            + "\n\n"
            + "("
            + str(num_fullstack_users)
            + ")"
            + bold("/" + str(user_sets.get_party_max_size()))
            + "\n"
            + user_sets.get_user_list_string()
        )
    else:
        new_message = (
            ""
            + msg
            + "\n\n"
            + "sadge/"
            + str(user_sets.get_party_max_size())
            + " <:viper:725612569716326422>"
        )

    return new_message
