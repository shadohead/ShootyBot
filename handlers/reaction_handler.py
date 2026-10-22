import logging
import asyncio
import copy
from contextlib import asynccontextmanager
from functools import wraps
from datetime import timedelta
from typing import Optional, Union
import discord
from discord.ext import commands
from context_manager import context_manager
from handlers.message_formatter import party_status_message
from data_manager import data_manager
from database import database_manager
from config import EMOJI, MESSAGES
from utils import parse_henrik_timestamp

# Emojis that join the party and therefore define membership when we rebuild
# state from a message's reactions after a restart.
_PARTY_EMOJIS = {EMOJI["THUMBS_UP"], EMOJI["FULL_STACK"], EMOJI["READY"]}

# Only rebuild state from a *recent* session message on startup. A channel's
# saved current_st_message_id can be days/weeks old (the DB keeps many sessions
# that were never explicitly ended); reviving those would resurrect long-dead
# parties and — because they'd report as "active" forever — permanently wedge
# the auto-update session guard. 12h comfortably covers a real gaming night.
RESTORE_MAX_AGE_HOURS = 12


async def add_react_options(message: discord.Message) -> None:
    """Add reaction options to a message"""
    await message.add_reaction(EMOJI["THUMBS_UP"])
    await message.add_reaction(EMOJI["FULL_STACK"])
    await message.add_reaction(EMOJI["REFRESH"])
    await message.add_reaction(EMOJI["MENTION"])


async def restore_party_state_from_reactions(bot: commands.Bot) -> int:
    """Rebuild in-memory party state from Discord after a restart.

    Restore a matching SQLite snapshot, including the initiator, guests and
    manual edits; replay only reaction changes since that snapshot. Older
    installations without snapshots fall back to an atomic reaction rebuild.
    An ended or stale session is never revived. All reads finish before live
    state changes, so a failed recovery preserves memory and the saved queue.

    Returns the number of channels whose state was restored.
    """
    restored = 0
    for settings in database_manager.get_all_channel_settings():
        message_id = settings.get("current_st_message_id")
        channel_id = settings.get("channel_id")
        if not message_id or not channel_id:
            continue

        # Skip stale sessions (snowflake carries the message's creation time),
        # so we don't revive long-dead parties or wedge the update guard.
        age = discord.utils.utcnow() - discord.utils.snowflake_time(message_id)
        if age > timedelta(hours=RESTORE_MAX_AGE_HOURS):
            logging.info(
                f"Restore: session message in channel {channel_id} is too old "
                f"({age}) — skipping"
            )
            continue

        # Ending a session leaves current_st_message_id (and the reactions) in
        # place, so only rebuild when the channel still has a recent open
        # session - otherwise an ended party would come back on every restart,
        # or get re-linked to an ancient never-ended session.
        open_session = database_manager.get_open_session_for_channel(channel_id)
        session_start = parse_henrik_timestamp((open_session or {}).get("start_time"))
        if session_start is None or (
                discord.utils.utcnow() - session_start > timedelta(hours=RESTORE_MAX_AGE_HOURS)):
            logging.info(
                f"Restore: no recent open session in channel {channel_id} - skipping"
            )
            continue

        shooty_context = context_manager.get_context(channel_id)
        if shooty_context.__dict__.get("_party_recovery_complete"):
            continue
        shooty_context.__dict__["_party_recovery_pending"] = True
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
        async with party_lock(shooty_context):
            if shooty_context.__dict__.get("_party_recovery_complete"):
                continue
            # Stage all network reads. A failed/partial reaction fetch must not
            # clear an existing queue or overwrite its durable snapshot.
            staged = copy.copy(shooty_context)
            staged.channel = channel
            staged.current_st_message_id = message_id
            staged.current_session_id = open_session["session_id"]
            try:
                snapshot = database_manager.get_party_state(channel_id)
                if snapshot is not None and (
                        snapshot["message_id"] == message_id and
                        snapshot["session_id"] == open_session["session_id"]):
                    await _restore_snapshot(staged, snapshot, bot)
                    await _reconcile_reactions(message, staged)
                else:
                    await _rebuild_users_from_reactions(message, staged, bot)
            except Exception as e:
                logging.warning("Restore: preserving queue in channel %s: %s", channel_id, e)
                continue

            shooty_context.channel = channel
            shooty_context.current_st_message_id = message_id
            for attr in ("bot_soloq_user_set", "bot_fullstack_user_set", "bot_ready_user_set",
                         "plus_ones", "reaction_users", "party_started_message_id"):
                setattr(shooty_context, attr, getattr(staged, attr))
            shooty_context.current_session_id = open_session["session_id"]
            shooty_context.__dict__["_party_recovery_pending"] = False
            shooty_context.__dict__["_party_recovery_complete"] = True
            try:
                await update_party_message(message, shooty_context)
            except discord.HTTPException:
                logging.warning("Restore: queue recovered but message refresh failed in %s", channel_id)

        # Re-link the still-open session (end_time IS NULL) so /stend & recap work
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


@asynccontextmanager
async def party_lock(context):
    """Serialize state changes; allow /st to call the locked end helper."""
    task = asyncio.current_task()
    if context.__dict__.get("_party_lock_owner") is task:
        yield
        return
    lock = context.__dict__.setdefault("_party_event_lock", asyncio.Lock())
    async with lock:
        context.__dict__["_party_lock_owner"] = task
        try:
            yield
        finally:
            context.__dict__.pop("_party_lock_owner", None)


async def ensure_party_recovered(bot, context):
    if context.__dict__.get("_party_recovery_pending"):
        await restore_party_state_from_reactions(bot)
        if context.__dict__.get("_party_recovery_pending"):
            raise RuntimeError("Party recovery incomplete; preserving the saved queue")


def serialized_party_command(callback):
    @wraps(callback)
    async def wrapped(self, ctx, *args, **kwargs):
        ready = getattr(self.bot, "_party_state_ready", None)
        if isinstance(ready, asyncio.Event):
            await ready.wait()
        context = context_manager.get_context(ctx.channel.id)
        await ensure_party_recovered(self.bot, context)
        async with party_lock(context):
            return await callback(self, ctx, *args, **kwargs)
    return wrapped


async def update_party_message(message, context):
    """Persist first; serialize edits and render current state inside the lock."""
    context_manager.save_context(context.channel_id)
    async with context.__dict__.setdefault("_party_message_lock", asyncio.Lock()):
        if message.id != context.current_st_message_id:
            return
        await message.edit(content=party_status_message(True, context),
                           allowed_mentions=discord.AllowedMentions.none())


async def refresh_party_message(channel, context):
    """Common path for queue commands as well as reactions/voice changes."""
    context_manager.save_context(context.channel_id)
    if context.current_st_message_id:
        try:
            message = await channel.fetch_message(context.current_st_message_id)
            await update_party_message(message, context)
        except discord.NotFound:
            logging.warning("Party message no longer exists in channel %s", context.channel_id)


async def repost_party_message(message, context):
    """Move the queue to a new controlled post without starting a new session."""
    async with party_lock(context):
        if message.id != context.current_st_message_id:
            return
        previous_id = context.current_st_message_id
        previous_start_id = context.party_started_message_id
        previous_reactions = context.reaction_users
        replacement = None
        try:
            replacement = await message.reply(
                party_status_message(False, context),
                allowed_mentions=discord.AllowedMentions.none())
            await add_react_options(replacement)
            context.current_st_message_id = replacement.id
            context.party_started_message_id = previous_start_id or previous_id
            # Membership remains in the snapshot. Reactions on this new post
            # start empty, so recovery must not treat old reactions as removed.
            context.reaction_users = {}
            if not context_manager.save_context(context.channel_id):
                raise RuntimeError("Could not persist reposted party message")
        except Exception:
            context.current_st_message_id = previous_id
            context.party_started_message_id = previous_start_id
            context.reaction_users = previous_reactions
            if replacement is not None:
                try:
                    await replacement.delete()
                except discord.HTTPException:
                    logging.warning("Could not remove failed party repost in channel %s", context.channel_id)
            raise
        logging.info("Reposted party in channel %s from message %s to %s",
                     context.channel_id, previous_id, replacement.id)


async def retire_party_message(channel, context):
    """Show the ended queue, then stop accepting reactions on that message."""
    try:
        if channel:
            await refresh_party_message(channel, context)
    except discord.HTTPException:
        logging.warning("Could not refresh ended party in channel %s", context.channel_id)
    finally:
        context.current_st_message_id = None
        context.party_started_message_id = None
        context.reaction_users = {}
        context_manager.save_context(context.channel_id)


async def _reaction_members(message):
    members = {emoji: {} for emoji in _PARTY_EMOJIS}
    for reaction in message.reactions:
        emoji = str(reaction.emoji)
        if emoji not in _PARTY_EMOJIS:
            continue
        async for user in reaction.users():
            if user.bot:
                continue
            guild = getattr(message.channel, "guild", None)
            members[emoji][user.id] = (guild.get_member(user.id) or user) if guild else user
    return members


def apply_party_reaction(context, user, emoji, added):
    """Apply one delta; remember both reactions when soloq takes precedence."""
    ids = context.reaction_users.setdefault(emoji, set())
    if added:
        ids.add(user.id)
    else:
        ids.discard(user.id)
    if emoji == EMOJI["READY"]:
        if added:
            context.bot_ready_user_set.add(user)
        else:
            context.bot_ready_user_set.discard(user)
    elif added:
        if emoji == EMOJI["THUMBS_UP"]:
            context.add_soloq_user(user)
        else:
            context.add_fullstack_user(user)
    else:
        if emoji == EMOJI["THUMBS_UP"]:
            context.remove_soloq_user(user)
            if user.id in context.reaction_users.get(EMOJI["FULL_STACK"], set()):
                context.add_fullstack_user(user)
        else:
            context.remove_fullstack_user(user)
        if user not in context.bot_soloq_user_set | context.bot_fullstack_user_set:
            context.remove_plus_ones(user)
            context.bot_ready_user_set.discard(user)


async def _rebuild_users_from_reactions(message, shooty_context, bot) -> None:
    """Legacy recovery: publish the new sets only after every read succeeds."""
    members = await _reaction_members(message)
    soloq = set(members[EMOJI["THUMBS_UP"]].values())
    fullstack = set(members[EMOJI["FULL_STACK"]].values()) - soloq
    shooty_context.bot_soloq_user_set = soloq
    shooty_context.bot_fullstack_user_set = fullstack
    shooty_context.bot_ready_user_set = set(members[EMOJI["READY"]].values())
    shooty_context.plus_ones = {}
    shooty_context.reaction_users = {emoji: set(users) for emoji, users in members.items()}


async def _restore_snapshot(context, snapshot, bot):
    """Resolve saved IDs before publishing any state; preserve guests and starter."""
    fields = ("soloq", "fullstack", "ready")
    ids = set().union(*(snapshot[field] for field in fields))
    guild = getattr(context.channel, "guild", None)
    users = {}
    for user_id in ids:
        user = guild.get_member(user_id) if guild else None
        if user is None:
            user = await bot.fetch_user(user_id)
        users[user_id] = user
    for field, attr in zip(fields, ("bot_soloq_user_set", "bot_fullstack_user_set", "bot_ready_user_set")):
        setattr(context, attr, {users[user_id] for user_id in snapshot[field]})
    context.plus_ones = {int(uid): count for uid, count in snapshot["plus_ones"].items()}
    context.reaction_users = {emoji: set(ids) for emoji, ids in snapshot["reaction_users"].items()}
    context.party_started_message_id = snapshot.get('party_started_message_id') or snapshot['message_id']


async def _reconcile_reactions(message, context):
    """Replay only changes since the snapshot, retaining manual queue edits."""
    members = await _reaction_members(message)
    known = {user.id: user for user in context.bot_soloq_user_set |
             context.bot_fullstack_user_set | context.bot_ready_user_set}
    known.update({uid: user for users in members.values() for uid, user in users.items()})
    # Removals before additions handles switching from one queue to another.
    for emoji, users in members.items():
        for uid in context.reaction_users.get(emoji, set()) - set(users):
            # A kicked user may exist only in the reaction baseline.
            user = known.get(uid) or discord.Object(id=uid)
            apply_party_reaction(context, user, emoji, False)
    for emoji, users in members.items():
        for uid in set(users) - context.reaction_users.get(emoji, set()):
            apply_party_reaction(context, users[uid], emoji, True)


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
        await update_party_message(message, shooty_context)

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

        # A new /st may have started while fetch_message was in flight.
        if payload.message_id != shooty_context.current_st_message_id:
            return None
        # Keep a live channel reference so voice-channel presence can be resolved
        shooty_context.channel = channel
        return message, member, shooty_context

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        ready = getattr(self.bot, "_party_state_ready", None)
        if isinstance(ready, asyncio.Event):
            await ready.wait()
        context = context_manager.get_context(payload.channel_id)
        await ensure_party_recovered(self.bot, context)
        async with party_lock(context):
            await self._on_raw_reaction_add(payload)

    async def _on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle when users add reactions (cache-independent)."""
        resolved = await self._resolve_reaction(payload)
        if resolved is None:
            return
        message, user, shooty_context = resolved
        emoji = str(payload.emoji)

        logging.info(
            f"Reaction added: {emoji} by {user.name} in channel {payload.channel_id}"
        )

        if emoji in _PARTY_EMOJIS:
            apply_party_reaction(shooty_context, user, emoji, True)
            # Queue persistence/display must not depend on participation stats.
            await self._update_party_message(message, shooty_context)
            await self.bot.update_status_with_queue_count()
            await self._track_session_participation(shooty_context, user)

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
        ready = getattr(self.bot, "_party_state_ready", None)
        if isinstance(ready, asyncio.Event):
            await ready.wait()
        context = context_manager.get_context(payload.channel_id)
        await ensure_party_recovered(self.bot, context)
        async with party_lock(context):
            await self._on_raw_reaction_remove(payload)

    async def _on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle when users remove reactions (cache-independent)."""
        resolved = await self._resolve_reaction(payload)
        if resolved is None:
            return
        message, user, shooty_context = resolved
        emoji = str(payload.emoji)

        logging.info(
            f"Reaction removed: {emoji} by {user.name} in channel {payload.channel_id}"
        )

        if emoji in _PARTY_EMOJIS:
            apply_party_reaction(shooty_context, user, emoji, False)
            await self._update_party_message(message, shooty_context)
            await self.bot.update_status_with_queue_count()

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
        """Repost current status with controls, preserving the existing queue."""
        context = context_manager.get_context(message.channel.id)
        await repost_party_message(message, context)
        await self.bot.update_status_with_queue_count()

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
