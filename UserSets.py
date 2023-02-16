from DiscordConfig import *
from EventHandler.MessageFormatter import *

# Class which holds all user data sets and setter/getters and associated message formatting requiring the user sets
class UserSets:

    def __init__(self) -> None:
        # set with all the users in the shooty crew
        self.bot_soloq_user_set = set() 
        # set with all the full stack only users in the shooty crew
        self.bot_fullstack_user_set = set()
        # set with all players who said they're ready to play right now
        self.bot_ready_user_set = set()

        
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


    def bold_readied_user(self, user):
        if user in self.bot_ready_user_set:
            return "**" + user.name + "**"
        else:
            return user.name


    def italics(self, input_str):
        return "*" + input_str + "*"

    ###
    # General Info Functions
    ###


    def get_user_list_string(self):
        result_string = ''

        # join both sets, print once based on which set the user came from

        all_users_set = self.bot_soloq_user_set.union(self.bot_fullstack_user_set)

        for index, user in enumerate(all_users_set):
            if user in self.bot_fullstack_user_set and user not in self.bot_soloq_user_set:
                result_string += italics(self.bold_readied_user(user))
            else:
                result_string += self.bold_readied_user(user)
            if index < len(all_users_set) - 1:
                result_string += ", "

        return result_string

    
    # DM functionality still not working yet
    async def dm_all_users_except_caller(self, user_who_called_command):
        for user in self.bot_soloq_user_set.union(self.bot_fullstack_user_set).discard(user_who_called_command):
            await user.send(f"You have been summoned by {user_who_called_command}.")
