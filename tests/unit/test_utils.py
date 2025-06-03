import pytest
from unittest.mock import Mock

from utils import resolve_role, resolve_voice_channel


def _mock_guild():
    guild = Mock()
    guild.roles = []
    guild.voice_channels = []
    guild.get_role = Mock(return_value=None)
    guild.get_channel = Mock(return_value=None)
    return guild


def test_resolve_role_by_mention():
    guild = _mock_guild()
    role = Mock()
    role.id = 1
    guild.get_role.return_value = role
    assert resolve_role(guild, "<@&1>") is role
    guild.get_role.assert_called_with(1)


def test_resolve_role_by_name():
    guild = _mock_guild()
    role = Mock()
    role.name = "Admin"
    guild.roles = [role]
    assert resolve_role(guild, "Admin") is role


def test_resolve_voice_channel_by_mention():
    guild = _mock_guild()
    channel = Mock()
    channel.id = 5
    guild.get_channel.return_value = channel
    assert resolve_voice_channel(guild, "<#5>") is channel
    guild.get_channel.assert_called_with(5)


def test_resolve_voice_channel_by_name():
    guild = _mock_guild()
    vc = Mock()
    vc.name = "General"
    guild.voice_channels = [vc]
    assert resolve_voice_channel(guild, "General") is vc
