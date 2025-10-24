from typing import Optional, List
from context_manager import ShootyContext
from config import DEFAULT_MSG, MESSAGES

def get_ping_shooty_message(role_code: Optional[str]) -> str:
    """Get the initial ping message for starting a session."""
    if not role_code or not role_code.strip():
        return MESSAGES["NO_ROLE"]

    return f"{DEFAULT_MSG}{role_code}"

def get_kicked_user_message(kicked_usernames_list: List[str]) -> str:
    """Get message for kicked users"""
    return "Kicked: " + str(kicked_usernames_list)

def get_max_party_size_message(party_size: int) -> str:
    """Get message for party size setting"""
    return f"Current party size: {party_size}"

def bold(text: str) -> str:
    """Make text bold for Discord"""
    return f"**{text}**"

def italics(text: str) -> str:
    """Make text italic for Discord"""
    return f"*{text}*"

def party_status_message(is_ping: bool, user_sets: ShootyContext) -> str:
    """
    Generate the party status message

    Args:
        is_ping: If True, include role mention in message
        user_sets: ShootyContext object with user data
    """
    
    num_soloq_users = user_sets.get_soloq_user_count()
    num_fullstack_users = user_sets.get_fullstack_user_count()
    num_unique_users = user_sets.get_unique_user_count()
    party_max_size = user_sets.get_party_max_size()
    
    # Build base message
    if is_ping and user_sets.role_code:
        msg = DEFAULT_MSG + user_sets.role_code
    else:
        msg = DEFAULT_MSG
    
    # Generate status based on party composition
    if num_unique_users >= party_max_size:
        # Party is full
        new_message = (
            msg + "\n\n" +
            bold(f"{num_unique_users}/{party_max_size}") +
            MESSAGES["PARTY_FULL_SUFFIX"] + "\n" +
            user_sets.get_user_list_string()
        )
    elif num_soloq_users > 0 and num_unique_users > num_soloq_users:
        # Mixed solo and fullstack
        new_message = (
            msg + "\n\n" +
            bold(str(num_soloq_users)) +
            f"({num_unique_users})" +
            bold(f"/{party_max_size}") + "\n" +
            user_sets.get_user_list_string()
        )
    elif num_soloq_users > 0:
        # Only solo queue users
        new_message = (
            msg + "\n\n" +
            bold(f"{num_soloq_users}/{party_max_size}") + "\n" +
            user_sets.get_user_list_string()
        )
    elif num_fullstack_users > 0:
        # Only fullstack users
        new_message = (
            msg + "\n\n" +
            f"({num_fullstack_users})" +
            bold(f"/{party_max_size}") + "\n" +
            user_sets.get_user_list_string()
        )
    else:
        # No users
        new_message = (
            msg + "\n\n" +
            MESSAGES["PARTY_EMPTY_SUFFIX"].format(size=party_max_size)
        )
    
    return new_message