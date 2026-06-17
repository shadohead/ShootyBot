import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import discord
from handlers.reaction_handler import (
    ReactionHandler,
    add_react_options,
    restore_party_state_from_reactions,
)
from config import EMOJI, MESSAGES


class _AsyncIter:
    """Minimal async iterator to stand in for discord's reaction.users()."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def make_raw_payload(*, user_id=111, channel_id=222, message_id=555,
                     emoji=EMOJI["THUMBS_UP"], member=None):
    """Build a fake RawReactionActionEvent payload."""
    payload = Mock()
    payload.user_id = user_id
    payload.channel_id = channel_id
    payload.message_id = message_id
    payload.emoji = emoji  # str(emoji) yields the emoji string
    payload.member = member
    return payload


class TestAddReactOptions:
    """Test the add_react_options helper function"""
    
    @pytest.mark.asyncio
    async def test_add_react_options(self):
        """Test adding reaction options to a message"""
        mock_message = AsyncMock()
        
        await add_react_options(mock_message)
        
        # Verify all required reactions were added
        expected_reactions = [
            EMOJI["THUMBS_UP"],
            EMOJI["FULL_STACK"], 
            EMOJI["REFRESH"],
            EMOJI["MENTION"]
        ]
        
        assert mock_message.add_reaction.call_count == len(expected_reactions)
        for emoji in expected_reactions:
            mock_message.add_reaction.assert_any_call(emoji)


class TestReactionHandler:
    """Simplified test cases for ReactionHandler class"""
    
    @pytest.fixture
    def handler(self):
        """Create a ReactionHandler instance with mocked bot"""
        bot = Mock()
        bot.user = Mock(id=999999999)
        return ReactionHandler(bot)
    
    @pytest.mark.asyncio
    async def test_ignore_own_reactions(self, handler):
        """The bot's own reactions (matched by user id) are ignored."""
        payload = make_raw_payload(user_id=handler.bot.user.id)
        assert await handler.on_raw_reaction_add(payload) is None
        assert await handler.on_raw_reaction_remove(payload) is None

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_ignore_other_bot_reactions(self, mock_context_manager, handler):
        """Reactions from other bot accounts are ignored."""
        ctx = Mock()
        ctx.current_st_message_id = 555
        mock_context_manager.get_context.return_value = ctx

        channel = AsyncMock()
        channel.fetch_message = AsyncMock(return_value=AsyncMock())
        handler.bot.get_channel = Mock(return_value=channel)

        payload = make_raw_payload(member=Mock(id=111, name="OtherBot", bot=True))
        assert await handler.on_raw_reaction_add(payload) is None

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_ignore_when_no_session_message(self, mock_context_manager, handler):
        """No current session message -> nothing to update."""
        ctx = Mock()
        ctx.current_st_message_id = None
        mock_context_manager.get_context.return_value = ctx
        handler.bot.get_channel = Mock()

        payload = make_raw_payload(member=Mock(id=111, name="U", bot=False))
        assert await handler.on_raw_reaction_add(payload) is None
        handler.bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_ignore_outdated_messages(self, mock_context_manager, handler):
        """Reactions on a message other than the latest one are ignored."""
        ctx = Mock()
        ctx.current_st_message_id = 999  # different from payload.message_id
        mock_context_manager.get_context.return_value = ctx
        handler.bot.get_channel = Mock()

        payload = make_raw_payload(message_id=123,
                                   member=Mock(id=111, name="U", bot=False))
        assert await handler.on_raw_reaction_add(payload) is None
        handler.bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.party_status_message', return_value="updated")
    @patch('handlers.reaction_handler.context_manager')
    async def test_raw_add_thumbs_up_adds_soloq(
        self, mock_context_manager, mock_status, handler
    ):
        """👍 on the session message adds the user to solo queue and re-renders."""
        ctx = Mock()
        ctx.current_st_message_id = 555
        ctx.current_session_id = None  # short-circuit participation tracking
        ctx.is_soloq_user.return_value = False
        mock_context_manager.get_context.return_value = ctx

        message = Mock()
        message.edit = AsyncMock()
        channel = Mock()
        channel.fetch_message = AsyncMock(return_value=message)
        handler.bot.get_channel = Mock(return_value=channel)
        handler.bot.update_status_with_queue_count = AsyncMock()

        member = Mock(id=111, name="Player", bot=False)
        payload = make_raw_payload(emoji=EMOJI["THUMBS_UP"], member=member)

        await handler.on_raw_reaction_add(payload)

        ctx.add_soloq_user.assert_called_once_with(member)
        message.edit.assert_awaited_once_with(content="updated")
        handler.bot.update_status_with_queue_count.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.party_status_message', return_value="updated")
    @patch('handlers.reaction_handler.context_manager')
    async def test_raw_remove_thumbs_up_removes_soloq(
        self, mock_context_manager, mock_status, handler
    ):
        """Removing 👍 removes the user from solo queue (resolved without member)."""
        ctx = Mock()
        ctx.current_st_message_id = 555
        ctx.is_soloq_user.return_value = True
        mock_context_manager.get_context.return_value = ctx

        message = Mock()
        message.edit = AsyncMock()
        guild = Mock()
        member = Mock(id=111, name="Player", bot=False)
        guild.get_member = Mock(return_value=member)
        channel = Mock()
        channel.guild = guild
        channel.fetch_message = AsyncMock(return_value=message)
        handler.bot.get_channel = Mock(return_value=channel)
        handler.bot.update_status_with_queue_count = AsyncMock()

        # No member on remove payloads — handler must resolve via guild
        payload = make_raw_payload(emoji=EMOJI["THUMBS_UP"], member=None)

        await handler.on_raw_reaction_remove(payload)

        guild.get_member.assert_called_once_with(111)
        ctx.remove_soloq_user.assert_called_once_with(member)
        ctx.remove_plus_ones.assert_called_once_with(member)
        message.edit.assert_awaited_once_with(content="updated")


    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.data_manager')
    async def test_track_session_participation(self, mock_data_manager, handler):
        """Test session participation tracking"""
        # Setup context with active session
        mock_context = Mock()
        mock_context.current_session_id = "session_123"
        
        # Setup session
        mock_session = Mock()
        mock_session.session_id = "session_123"
        mock_session.add_participant = Mock()
        mock_sessions = MagicMock()
        mock_sessions.get.return_value = mock_session
        mock_data_manager.sessions = mock_sessions
        
        # Setup user data
        mock_user_data = Mock()
        mock_data_manager.get_user.return_value = mock_user_data
        
        # Test user
        user = Mock(id=123456789, name="TestUser")
        
        # Call the method
        await handler._track_session_participation(mock_context, user)
        
        # Verify tracking occurred
        mock_session.add_participant.assert_called_once_with(123456789)
        mock_user_data.add_session_to_history.assert_called_once_with("session_123")
        mock_data_manager.save_session.assert_called_once_with("session_123")
        mock_data_manager.save_user.assert_called_once_with(123456789)
    
    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.data_manager')
    async def test_track_session_no_active_session(self, mock_data_manager, handler):
        """Test session tracking when no active session"""
        # Setup context without active session
        mock_context = Mock()
        mock_context.current_session_id = None
        
        user = Mock(id=123456789)
        
        # Call the method
        await handler._track_session_participation(mock_context, user)
        
        # Verify nothing was tracked
        mock_data_manager.sessions.get.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_refresh_status(self, handler, mock_discord_message):
        """Test refresh status functionality"""
        # Setup
        message = mock_discord_message
        message.channel.id = 111222333
        
        mock_ctx = AsyncMock()
        handler.bot.get_context = AsyncMock(return_value=mock_ctx)
        
        mock_session_cog = AsyncMock()
        handler.bot.get_cog = Mock(return_value=mock_session_cog)
        
        # Call the method
        await handler._refresh_status(message)
        
        # Verify
        handler.bot.get_context.assert_called_once_with(message)
        handler.bot.get_cog.assert_called_once_with('SessionCommands')
        mock_session_cog.session_status.assert_called_once_with(mock_ctx)

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_refresh_status_context_failure(self, mock_context_manager, handler):
        """Exception propagates if context cannot be fetched"""
        message = Mock()
        message.channel = Mock(id=123)

        mock_context_manager.get_context.side_effect = Exception("fail")
        handler.bot.get_context = AsyncMock(return_value=AsyncMock())

        with pytest.raises(Exception):
            await handler._refresh_status(message)

    @pytest.mark.asyncio
    async def test_refresh_status_missing_cog(self, handler):
        """Gracefully handle missing SessionCommands cog"""
        message = Mock()
        message.channel = Mock(id=456)

        handler.bot.get_context = AsyncMock(return_value=AsyncMock())
        handler.bot.get_cog = Mock(return_value=None)

        await handler._refresh_status(message)
        handler.bot.get_context.assert_called_once_with(message)
        handler.bot.get_cog.assert_called_once_with('SessionCommands')
    
    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_mention_party_no_members(self, mock_context_manager, handler, mock_discord_message):
        """Test mention party with no members"""
        # Setup
        mock_context = Mock()
        mock_context.bot_soloq_user_set = set()
        mock_context.bot_fullstack_user_set = set()
        mock_context_manager.get_context.return_value = mock_context
        
        message = mock_discord_message
        message.channel = AsyncMock()
        
        # Call the method
        await handler._mention_party(message)
        
        # Verify
        message.channel.send.assert_called_once_with(MESSAGES["NO_MEMBERS"])
    
    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_mention_party_with_members(self, mock_context_manager, handler, discord_member_factory, mock_discord_message):
        """Test mention party with members"""
        # Setup
        user1 = discord_member_factory(user_id=111, name="User1")
        user1.bot = False
        user2 = discord_member_factory(user_id=222, name="User2")
        user2.bot = False
        bot_user = discord_member_factory(user_id=999, name="Bot")
        bot_user.bot = True
        
        mock_context = Mock()
        mock_context.bot_soloq_user_set = {user1, bot_user}
        mock_context.bot_fullstack_user_set = {user2}
        mock_context_manager.get_context.return_value = mock_context
        
        message = mock_discord_message
        message.channel = AsyncMock()
        
        # Call the method
        await handler._mention_party(message)
        
        # Verify - should mention only non-bot users
        call_args = message.channel.send.call_args[0][0]
        assert "<@111>" in call_args
        assert "<@222>" in call_args
        assert "<@999>" not in call_args  # Bot user should be excluded

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_mention_party_deduplicate_and_ignore_bots(self, mock_context_manager, handler):
        """Duplicate users should be mentioned once and bots ignored"""
        user1 = Mock(mention="<@111>", bot=False)
        user2 = Mock(mention="<@222>", bot=False)
        bot_user = Mock(mention="<@333>", bot=True)

        mock_context = Mock()
        mock_context.bot_soloq_user_set = {user1, user2, bot_user}
        mock_context.bot_fullstack_user_set = {user2}
        mock_context_manager.get_context.return_value = mock_context

        message = Mock()
        message.channel = AsyncMock()

        await handler._mention_party(message)

        call_args = message.channel.send.call_args[0][0].split()
        assert call_args.count("<@111>") == 1
        assert call_args.count("<@222>") == 1
        assert "<@333>" not in call_args


class TestVoiceStateUpdate:
    """Test cases for the on_voice_state_update listener"""

    @pytest.fixture
    def handler(self):
        bot = Mock()
        bot.user = Mock(id=999999999)
        bot.get_channel = Mock()
        bot.update_status_with_queue_count = AsyncMock()
        return ReactionHandler(bot)

    def _voice_state(self, channel):
        state = Mock(spec=discord.VoiceState)
        state.channel = channel
        return state

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_ignores_non_channel_changes(self, mock_context_manager, handler):
        """Mute/deafen updates (same channel) should not trigger a refresh"""
        same_channel = Mock()
        member = Mock(spec=discord.Member)

        await handler.on_voice_state_update(
            member,
            self._voice_state(same_channel),
            self._voice_state(same_channel),
        )

        handler.bot.get_channel.assert_not_called()
        handler.bot.update_status_with_queue_count.assert_not_called()

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.party_status_message', return_value="updated")
    @patch('handlers.reaction_handler.context_manager')
    async def test_refreshes_message_for_queued_member(
        self, mock_context_manager, mock_status, handler
    ):
        """A queued member joining voice should re-render that channel's message"""
        guild = Mock()
        member = Mock(spec=discord.Member)
        member.guild = guild

        context = Mock()
        context.channel_id = 555
        context.current_st_message_id = 777
        context.bot_soloq_user_set = {member}
        context.bot_fullstack_user_set = set()
        mock_context_manager.contexts = {555: context}

        message = AsyncMock()
        channel = AsyncMock()
        channel.guild = guild
        channel.fetch_message.return_value = message
        handler.bot.get_channel.return_value = channel

        await handler.on_voice_state_update(
            member,
            self._voice_state(None),
            self._voice_state(Mock()),
        )

        channel.fetch_message.assert_awaited_once_with(777)
        message.edit.assert_awaited_once_with(content="updated")
        assert context.channel == channel
        handler.bot.update_status_with_queue_count.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.context_manager')
    async def test_ignores_member_not_queued(self, mock_context_manager, handler):
        """A member who is not queued should not trigger any refresh"""
        guild = Mock()
        member = Mock(spec=discord.Member)
        member.guild = guild

        context = Mock()
        context.channel_id = 555
        context.current_st_message_id = 777
        context.bot_soloq_user_set = set()
        context.bot_fullstack_user_set = set()
        mock_context_manager.contexts = {555: context}

        await handler.on_voice_state_update(
            member,
            self._voice_state(None),
            self._voice_state(Mock()),
        )

        handler.bot.get_channel.assert_not_called()
        handler.bot.update_status_with_queue_count.assert_not_called()


class TestRestorePartyState:
    """Tests for rebuilding party state from reactions after a restart."""

    def _bot(self):
        bot = Mock()
        bot.user = Mock(id=999999999)
        return bot

    def _reaction(self, emoji, users):
        reaction = Mock()
        reaction.emoji = emoji
        reaction.users = Mock(return_value=_AsyncIter(users))
        return reaction

    def _recent_msg_id(self):
        """A snowflake whose embedded timestamp is 'now' (passes recency gate)."""
        return discord.utils.time_snowflake(discord.utils.utcnow())

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.database_manager')
    async def test_restore_rebuilds_soloq_and_relinks_session(self, mock_db):
        from context_manager import ShootyContext

        bot = self._bot()
        msg_id = self._recent_msg_id()
        mock_db.get_all_channel_settings.return_value = [
            {"channel_id": 555, "current_st_message_id": msg_id}
        ]
        mock_db.get_open_session_for_channel.return_value = {"session_id": "sess-1"}

        player = Mock(id=111, name="Player", bot=False)
        bot_user = Mock(id=999999999, name="Bot", bot=True)

        message = Mock()
        message.author = bot.user
        message.channel = Mock(guild=None)
        message.reactions = [self._reaction(EMOJI["THUMBS_UP"], [player, bot_user])]

        channel = Mock()
        channel.fetch_message = AsyncMock(return_value=message)
        bot.get_channel = Mock(return_value=channel)

        real_ctx = ShootyContext(555)
        with patch('handlers.reaction_handler.context_manager') as mock_cm:
            mock_cm.get_context.return_value = real_ctx
            restored = await restore_party_state_from_reactions(bot)

        assert restored == 1
        assert player in real_ctx.bot_soloq_user_set
        assert bot_user not in real_ctx.bot_soloq_user_set  # bots excluded
        assert real_ctx.current_st_message_id == msg_id
        assert real_ctx.current_session_id == "sess-1"

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.database_manager')
    async def test_restore_skips_stale_message(self, mock_db):
        """A weeks-old session message must NOT be revived (would wedge updates)."""
        bot = self._bot()
        # Snowflake 777 -> ~2015, far older than RESTORE_MAX_AGE_HOURS
        mock_db.get_all_channel_settings.return_value = [
            {"channel_id": 555, "current_st_message_id": 777}
        ]
        bot.get_channel = Mock()

        restored = await restore_party_state_from_reactions(bot)
        assert restored == 0
        bot.get_channel.assert_not_called()  # skipped before any fetch

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.database_manager')
    async def test_restore_skips_channels_without_message(self, mock_db):
        bot = self._bot()
        mock_db.get_all_channel_settings.return_value = [
            {"channel_id": 555, "current_st_message_id": None}
        ]
        bot.get_channel = Mock()

        restored = await restore_party_state_from_reactions(bot)
        assert restored == 0
        bot.get_channel.assert_not_called()

    @pytest.mark.asyncio
    @patch('handlers.reaction_handler.database_manager')
    async def test_restore_skips_deleted_message(self, mock_db):
        bot = self._bot()
        msg_id = self._recent_msg_id()
        mock_db.get_all_channel_settings.return_value = [
            {"channel_id": 555, "current_st_message_id": msg_id}
        ]
        channel = Mock()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(Mock(), "gone"))
        bot.get_channel = Mock(return_value=channel)

        with patch('handlers.reaction_handler.context_manager'):
            restored = await restore_party_state_from_reactions(bot)
        assert restored == 0


@pytest.mark.asyncio
async def test_setup():
    """Test the setup function"""
    mock_bot = AsyncMock()
    
    from handlers.reaction_handler import setup
    await setup(mock_bot)
    
    # Verify cog was added
    mock_bot.add_cog.assert_called_once()
    # Verify a ReactionHandler instance was passed
    from handlers.reaction_handler import ReactionHandler
    assert isinstance(mock_bot.add_cog.call_args[0][0], ReactionHandler)