import pytest
from unittest.mock import Mock
import discord

from utils import resolve_role, resolve_voice_channel, parse_henrik_timestamp
from datetime import timezone


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
    channel = Mock(spec=discord.VoiceChannel)
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


def test_parse_henrik_timestamp_iso():
    ts = "2024-01-01T00:00:00Z"
    dt = parse_henrik_timestamp(ts)
    assert dt.year == 2024
    assert dt.tzinfo == timezone.utc


def test_parse_henrik_timestamp_epoch_ms():
    ts_ms = 1609459200000  # 2021-01-01T00:00:00Z
    dt = parse_henrik_timestamp(ts_ms)
    assert dt.year == 2021
    assert dt.tzinfo == timezone.utc


def test_parse_henrik_timestamp_epoch_s_string():
    ts_s = "1609459200"  # 2021-01-01T00:00:00Z
    dt = parse_henrik_timestamp(ts_s)
    assert dt.year == 2021
    assert dt.tzinfo == timezone.utc
