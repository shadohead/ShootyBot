import logging
from DiscordConfig import *
from EventHandler.MessageFormatter import *
import json
import os

# Class which holds all user data sets and setter/getters and associated message formatting requiring the user sets


class ShootyContext:
    def __init__(self, channel_id) -> None:
        # Initialize instance variables

        # channel associated for lfg
        self.channel = channel_id

        # Load channel_data from a local JSON file
        self.channel_data = self.load_channel_data()

        # set with all the users in the shooty crew
        self.bot_soloq_user_set = set()
        # set with all the full stack only users in the shooty crew
        self.bot_fullstack_user_set = set()
        # set with all players who said they're ready to play right now
        self.bot_ready_user_set = set()

        # message_id of the most recent sts or st message
        self.current_st_message_id = None

        # role_id of the desired role to ping
        self.role_code = None

        # game name set for lfg
        self.game_name = None

        self.party_max_size = 5

        logging.info("Loaded json contents:" + str(self.channel_data))
        self.load_variables()

    def load_channel_data(self):
        if os.path.exists("channel_data.json"):
            with open("channel_data.json", "r") as file:
                return json.load(file)
        else:
            return {}

    def save_channel_data(self):
        with open("channel_data.json", "w") as file:
            json.dump(self.channel_data, file)

    def load_variables(self):
        if self.channel_data and self.channel:
            data = self.channel_data.get(str(self.channel))

            logging.info("Loaded data contents:" + str(data))

            if data:
                self.role_code = self.get_role_code(str(self.channel))
                self.game_name = self.get_game_name(str(self.channel))
                logging.info(
                    f"set role_code:{self.role_code}, game_name:{self.game_name}"
                )

    def set_channel_data(self, channel, role_code, game_name):
        self.role_code = role_code
        self.game_name = game_name
        self.channel = channel

        if self.channel not in self.channel_data:
            self.channel_data[self.channel] = {}

        self.channel_data[self.channel].update(
            {"role_code": self.role_code, "game_name": self.game_name}
        )
        self.save_channel_data()

    def get_channel_data(self, channel):
        if channel in self.channel_data:
            return self.channel_data[channel]
        return None

    def get_role_code(self, channel):
        data = self.get_channel_data(channel)
        if data:
            return data["role_code"]
        return None

    def get_game_name(self, channel):
        data = self.get_channel_data(channel)
        if data:
            return data["game_name"]
        return None

    ###
    # Solo Q User Functions
    ###

    def get_soloq_user_count(self):
        return len(self.bot_soloq_user_set)

    def add_soloq_user(self, user):
        self.bot_soloq_user_set.add(user)

    def is_soloq_user(self, user):
        return user in self.bot_soloq_user_set

    def remove_soloq_user(self, user):
        if user in self.bot_soloq_user_set:
            self.bot_soloq_user_set.remove(user)

    ###
    # Fullstack User Functions
    ###

    def get_fullstack_user_count(self):
        return len(self.bot_fullstack_user_set)

    def add_fullstack_user(self, user):
        self.bot_fullstack_user_set.add(user)

    def remove_fullstack_user(self, user):
        if user in self.bot_fullstack_user_set:
            self.bot_fullstack_user_set.remove(user)

    ###
    # Party Max Size Functions
    ###

    def set_party_max_size(self, size):
        self.party_max_size = size

    def get_party_max_size(self):
        return self.party_max_size

    ###
    # Macro Functions
    ###

    def get_unique_user_count(self):
        return len(self.bot_soloq_user_set.union(self.bot_fullstack_user_set))

    def reset_users(self):
        self.bot_soloq_user_set.clear()
        self.bot_fullstack_user_set.clear()
        self.bot_ready_user_set.clear()

    def remove_user_from_everything(self, user_names_list):
        kicked_usernames_list = []

        for username in user_names_list:
            for user in self.bot_soloq_user_set.copy():
                if user.name.startswith(username):
                    self.bot_soloq_user_set.remove(user)
                    kicked_usernames_list.append(user.name)

            for user in self.bot_fullstack_user_set.copy():
                if user.name.startswith(username):
                    self.bot_fullstack_user_set.remove(user)
                    kicked_usernames_list.append(user.name)

        return kicked_usernames_list

    ###
    # Formatting Functions
    ###

    def bold_readied_user(self, user, display_hashtag=False):
        user_name = ""

        if user in self.bot_ready_user_set:
            user_name = "**" + user.name + "**"
        elif display_hashtag and user in self.bot_ready_user_set:
            user_name = f"**{str(user)}**"  # shows hashtag
        elif display_hashtag:
            user_name = str(user)  # shows hashtag
        else:
            user_name = user.name

        return user_name

    def italics(self, input_str):
        return "*" + input_str + "*"

    ###
    # General Info Functions
    ###

    def get_user_list_string(self):
        result_string = ""

        # join both sets, logging.info once based on which set the user came from

        all_users_set = self.bot_soloq_user_set.union(self.bot_fullstack_user_set)

        for index, user in enumerate(all_users_set):
            if (
                user in self.bot_fullstack_user_set
                and user not in self.bot_soloq_user_set
            ):
                result_string += italics(self.bold_readied_user(user))
            else:
                result_string += self.bold_readied_user(user)
            if index < len(all_users_set) - 1:
                result_string += ", "

        return result_string

    def get_user_list_string_with_hashtag(self):
        result_string = ""

        # join both sets, logging.info once based on which set the user came from

        all_users_set = self.bot_soloq_user_set.union(self.bot_fullstack_user_set)

        for index, user in enumerate(all_users_set):
            if (
                user in self.bot_fullstack_user_set
                and user not in self.bot_soloq_user_set
            ):
                result_string += italics(self.bold_readied_user(user, True))
            else:
                result_string += self.bold_readied_user(user, True)
            if index < len(all_users_set) - 1:
                result_string += ", "

        return result_string

    # DM functionality still not working yet

    async def dm_all_users_except_caller(self, user_who_called_command):
        for user in self.bot_soloq_user_set.union(self.bot_fullstack_user_set).discard(
            user_who_called_command
        ):
            await user.send(f"You have been summoned by {user_who_called_command}.")
