from DiscordConfig import *


party_max_size = DEFAULT_PARTY_SIZE

###
# Party Max Size Functions
###


def set_party_max_size(size):
    global party_max_size
    party_max_size = size


def get_party_max_size():
    global party_max_size
    return party_max_size


