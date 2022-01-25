from DiscordConfig import *

bot_soloq_user_set = set()  # set with all the users in the shooty crew
# set with all the full stack only users in the shooty crew
bot_fullstack_user_set = set()
# set with all players who said they're ready to play right now
bot_ready_user_set = set()

party_max_size = DEFAULT_PARTY_SIZE

###
# General Info Functions
###


def get_user_list_string():
    result_string = ''

    for index, user in enumerate(bot_soloq_user_set):
        result_string += bold_readied_user(user)

        # if it's not the last player, add a comma
        if index < len(bot_soloq_user_set) + len(bot_fullstack_user_set) - 1:
            result_string += ", "

    for index, user in enumerate(bot_fullstack_user_set):
        result_string += italics(bold_readied_user(user))

        # if it's not the last player, add a comma
        if index < len(bot_fullstack_user_set) - 1:
            result_string += ", "

    return result_string

###
# Solo Q User Functions
###


def get_soloq_user_count():
    return len(bot_soloq_user_set)


def add_soloq_user(user):
    bot_soloq_user_set.add(user)


def is_soloq_user(user):
    return user in bot_soloq_user_set


def remove_soloq_user(user):
    if user in bot_soloq_user_set:
        bot_soloq_user_set.remove(user)

###
# Fullstack User Functions
###


def get_fullstack_user_count():
    return len(bot_fullstack_user_set)


def add_fullstack_user(user):
    bot_fullstack_user_set.add(user)


def remove_fullstack_user(user):
    if user in bot_fullstack_user_set:
        bot_fullstack_user_set.remove(user)

###
# Party Max Size Functions
###


def set_party_max_size(size):
    global party_max_size
    party_max_size = size


def get_party_max_size():
    global party_max_size
    return party_max_size

###
# Macro Functions
###


def reset_users():
    bot_soloq_user_set.clear()
    bot_fullstack_user_set.clear()
    bot_ready_user_set.clear()


def remove_user_from_everything(user_names_list):
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

    return kicked_usernames_list

###
# Formatting Functions
###


def bold_readied_user(user):
    if user in bot_ready_user_set:
        return "**" + user.name + "**"
    else:
        return user.name


def italics(input_str):
    return "*" + input_str + "*"
