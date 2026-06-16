import logging
from typing import Optional, Union
import discord
from discord.ext import commands
from context_manager import context_manager
from handlers.message_formatter import party_status_message
from data_manager import data_manager
from database import database_manager
from config import EMOJI, MESSAGES

# Emojis that join the party and therefore define membership when we rebuild
# state from a message's reactions after a restart.
_PARTY_EMOJIS = {EMOJI["THUMBS_UP"], EMOJI["FULL_STACK"], EMOJI["READY"]}


async def add_react_options(message: discord.Message) -> None:
    """Add reaction options to a message"""
    await message.add_reaction(EMOJI["THUMBS_UP"])
    await message.add_reaction(EMOJI["FULL_STACK"])
    await message.add_reaction(EMOJI["REFRESH"])
    await message.add_reaction(EMOJI["MENTION"])


async def restore_party_state_from_reactions(bot: commands.Bot) -> int:
    """Rebuild in-memory party state from Discord after a restart.

    Party membership (who reacted 👍 / 5️⃣ / ✅) is never stored in the
    database — the reactions on the bot's session message *are* the source of
    truth. On startup the bot's message cache is empty, so we walk every
    channel that has a saved ``current_st_message_id``, re-read its reactions,
    and repopulate the soloq / fullstack / ready sets. We also re-link the
    channel's still-open session so ``/stend`` keeps working.

    Returns the number of channels whose state was restored.
    """
    restored = 0
    for settings in database_manager.get_all_channel_settings():
        message_id = settings.get("current_st_message_id")
        channel_id = settings.get("channel_id")
        if not message_id or not channel_id:
            continue

        channel = bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logging.info(f"Restore: channel {channel_id} unavailable, skipping")
                continue

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            logging.info(f"Restore: session message {message_id} gone in {channel_id}")
            continue
        except discord.HTTPException as e:
            logging.warning(f"Restore: failed to fetch message in {channel_id}: {e}")
            continue

        # Only restore from our own session messages
        if message.author.id != bot.user.id:
            continue

        shooty_context = context_manager.get_context(channel_id)
        shooty_context.channel = channel
        shooty_context.current_st_message_id = message_id
        shooty_context.reset_users()

        try:
            await _rebuild_users_from_reactions(message, shooty_context, bot)
        except discord.HTTPException as e:
            logging.warning(f"Restore: failed reading reactions in {channel_id}: {e}")
            continue

        # Re-link the still-open session (end_time IS NULL) so /stend & recap work
        open_session = database_manager.get_open_session_for_channel(channel_id)
        if open_session:
            shooty_context.current_session_id = open_session["session_id"]

        member_count = len(
            shooty_context.bot_soloq_user_set | shooty_context.bot_fullstack_user_set
        )
        logging.info(
            f"Restored party state for channel {channel_id}: "
            f"{member_count} member(s), session="
            f"{getattr(shooty_context, 'current_session_id', None)}"
        )
        restored += 1

    if restored:
        logging.info(f"♻️ Restored party state for {restored} channel(s) after restart")
    return restored


async def _rebuild_users_from_reactions(message, shooty_context, bot) -> None:
    """Repopulate a context's user sets from the reactions on ``message``."""
    for reaction in message.reactions:
        emoji = str(reaction.emoji)
        if emoji not in _PARTY_EMOJIS:
            continue

        async for user in reaction.users():
            if user.bot:
                continue
            # Prefer the richer guild Member object for voice-presence checks
            member = user
            guild = getattr(message.channel, "guild", None)
            if guild is not None:
                member = guild.get_member(user.id) or user

            if emoji == EMOJI["THUMBS_UP"]:
                shooty_context.add_soloq_user(member)
            elif emoji == EMOJI["FULL_STACK"]:
                shooty_context.add_fullstack_user(member)
            elif emoji == EMOJI["READY"]:
                shooty_context.bot_ready_user_set.add(member)


class ReactionHandler(commands.Cog):
    """Handles all reaction-based interactions.

    Uses *raw* reaction events (``on_raw_reaction_add`` /
    ``on_raw_reaction_remove``) instead of the cache-backed
    ``on_reaction_add`` / ``on_reaction_remove``. The cached variants only fire
    when the reacted message is in the bot's in-memory message cache, which is
    empty after a restart — so reactions on an existing session message would
    silently stop updating the party. Raw events fire regardless of the cache.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _update_party_message(self, message: discord.Message, shooty_context) -> None:
        """Helper method to update party status message"""
        new_message = party_status_message(True, shooty_context)
        await message.edit(content=new_message)

    async def _resolve_reaction(
        self, payload: discord.RawReactionActionEvent
    ) -> Optional[tuple]:
        """Resolve a raw reaction payload to (message, member, shooty_context).

        Returns ``None`` (so the caller bails) when the reaction is the bot's
        own, isn't on the channel's current session message, or can't be
        resolved to a real member/message.
        """
        # Ignore the bot's own reactions (e.g. the initial option emojis)
        if payload.user_id == self.bot.user.id:
            return None

        channel_id = payload.channel_id
        shooty_context = context_manager.get_context(channel_id)

        # Cheap early-out: only the latest session message drives party state,
        # and this avoids fetching messages for unrelated reactions.
        if not shooty_context.current_st_message_id:
            return None
        if payload.message_id != shooty_context.current_st_message_id:
            return None

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                return None

        # Resolve the member. on_raw_reaction_add gives us payload.member in
        # guilds; on remove we must look the user up ourselves.
        member: Optional[Union[discord.Member, discord.User]] = payload.member
        if member is None:
            guild = getattr(channel, "guild", None)
            if guild is not None:
                member = guild.get_member(payload.user_id)
            if member is None:
                try:
                    member = await self.bot.fetch_user(payload.user_id)
                except discord.HTTPException:
                    return None

        if member is None or member.bot:
            return None

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return None

        # Keep a live channel reference so voice-channel presence can be resolved
        shooty_context.channel = channel
        return message, member, shooty_context

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle when users add reactions (cache-independent)."""
        resolved = await self._resolve_reaction(payload)
        if resolved is None:
            return
        message, user, shooty_context = resolved
        emoji = str(payload.emoji)

        logging.info(
            f"Reaction added: {emoji} by {user.name} in channel {payload.channel_id}"
        )

        # Handle thumbs up (solo queue)
        if emoji == EMOJI["THUMBS_UP"]:
            shooty_context.add_soloq_user(user)
            logging.info(f"Added {user.name} to solo queue")
            await self._track_session_participation(shooty_context, user)
            await self._update_party_message(message, shooty_context)
            await self.bot.update_status_with_queue_count()

        # Handle 5️⃣ (fullstack only)
        elif emoji == EMOJI["FULL_STACK"]:
            if not shooty_context.is_soloq_user(user):
                shooty_context.add_fullstack_user(user)
                logging.info(f"Added {user.name} to fullstack queue")
                await self._track_session_participation(shooty_context, user)
                await self._update_party_message(message, shooty_context)
                await self.bot.update_status_with_queue_count()

        # Handle ✅ (ready)
        elif emoji == EMOJI["READY"]:
            shooty_context.bot_ready_user_set.add(user)
            logging.info(f"Marked {user.name} as ready")
            await self._update_party_message(message, shooty_context)

        # Handle 🔄 (refresh)
        elif emoji == EMOJI["REFRESH"]:
            logging.info("Refresh emoji clicked")
            await self._refresh_status(message)

        # Handle 📣 (mention)
        elif emoji == EMOJI["MENTION"]:
            logging.info("Mention emoji clicked")
            await self._mention_party(message)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle when users remove reactions (cache-independent)."""
        resolved = await self._resolve_reaction(payload)
        if resolved is None:
            return
        message, user, shooty_context = resolved
        emoji = str(payload.emoji)

        logging.info(
            f"Reaction removed: {emoji} by {user.name} in channel {payload.channel_id}"
        )

        # Handle thumbs up removal (solo queue)
        if emoji == EMOJI["THUMBS_UP"] and shooty_context.is_soloq_user(user):
            shooty_context.remove_soloq_user(user)
            # Also remove plus ones when user leaves party
            shooty_context.remove_plus_ones(user)
            logging.info(f"Removed {user.name} from solo queue and cleared their plus ones")
            await self._update_party_message(message, shooty_context)
            await self.bot.update_status_with_queue_count()

        # Handle 5️⃣ removal (fullstack)
        elif emoji == EMOJI["FULL_STACK"] and user in shooty_context.bot_fullstack_user_set:
            shooty_context.remove_fullstack_user(user)
            # Also remove plus ones when user leaves party
            shooty_context.remove_plus_ones(user)
            logging.info(f"Removed {user.name} from fullstack queue and cleared their plus ones")
            await self._update_party_message(message, shooty_context)
            await self.bot.update_status_with_queue_count()

        # Handle ✅ removal (ready)
        elif emoji == EMOJI["READY"] and user in shooty_context.bot_ready_user_set:
            shooty_context.bot_ready_user_set.remove(user)
            logging.info(f"Unmarked {user.name} as ready")
            await self._update_party_message(message, shooty_context)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Re-render queue messages when a queued user joins/leaves voice."""
        # Only react to actual channel changes (join, leave, or move)
        if before.channel == after.channel:
            return

        refreshed_any = False
        for shooty_context in context_manager.contexts.values():
            # Skip channels that have no active message to update
            if not shooty_context.current_st_message_id:
                continue

            # Only act if this member is currently queued in this context
            queued_users = shooty_context.bot_soloq_user_set | shooty_context.bot_fullstack_user_set
            if member not in queued_users:
                continue

            channel = self.bot.get_channel(shooty_context.channel_id)
            if channel is None or getattr(channel, "guild", None) != member.guild:
                continue

            # Keep the channel reference fresh for voice-presence resolution
            shooty_context.channel = channel
            try:
                message = await channel.fetch_message(shooty_context.current_st_message_id)
                await self._update_party_message(message, shooty_context)
                refreshed_any = True
            except discord.NotFound:
                logging.info("Skipping voice update - shooty message no longer exists")
            except discord.HTTPException as e:
                logging.warning(f"Failed to refresh shooty message on voice update: {e}")

        if refreshed_any:
            await self.bot.update_status_with_queue_count()

    async def _refresh_status(self, message):
        """Refresh the party status message"""
        channel_id = message.channel.id
        shooty_context = context_manager.get_context(channel_id)

        # Create a fake context for the session status command
        ctx = await self.bot.get_context(message)

        # Get the session commands cog
        session_cog = self.bot.get_cog('SessionCommands')
        if session_cog:
            await session_cog.session_status(ctx)

    async def _mention_party(self, message):
        """Mention all party members"""
        channel_id = message.channel.id
        shooty_context = context_manager.get_context(channel_id)

        if not shooty_context.bot_soloq_user_set and not shooty_context.bot_fullstack_user_set:
            await message.channel.send(MESSAGES["NO_MEMBERS"])
            return

        mention_message = "".join(
            user.mention + " "
            for user in shooty_context.bot_soloq_user_set.union(shooty_context.bot_fullstack_user_set)
            if not user.bot
        )

        await message.channel.send(mention_message)

    async def _track_session_participation(self, shooty_context, user):
        """Track user participation in the current session"""
        if hasattr(shooty_context, 'current_session_id') and shooty_context.current_session_id:
            session = data_manager.sessions.get(shooty_context.current_session_id)
            if session:
                session.add_participant(user.id)
                data_manager.save_session(session.session_id)

                # Update user stats
                user_data = data_manager.get_user(user.id)
                user_data.add_session_to_history(session.session_id)
                data_manager.save_user(user.id)

                logging.info(f"Tracked participation for {user.name} in session {session.session_id}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReactionHandler(bot))
