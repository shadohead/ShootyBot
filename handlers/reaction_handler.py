import logging
from typing import Union
import discord
from discord.ext import commands
from context_manager import context_manager
from handlers.message_formatter import party_status_message
from data_manager import data_manager
from config import EMOJI, MESSAGES

async def add_react_options(message: discord.Message) -> None:
    """Add reaction options to a message"""
    await message.add_reaction(EMOJI["THUMBS_UP"])
    await message.add_reaction(EMOJI["FULL_STACK"])
    await message.add_reaction(EMOJI["REFRESH"])
    await message.add_reaction(EMOJI["MENTION"])

class ReactionHandler(commands.Cog):
    """Handles all reaction-based interactions"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _update_party_message(self, message: discord.Message, shooty_context) -> None:
        """Helper method to update party status message"""
        new_message = party_status_message(True, shooty_context)
        await message.edit(content=new_message)
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]) -> None:
        """Handle when users add reactions"""
        if user.bot or reaction.message.author != self.bot.user:
            return
        
        channel_id = reaction.message.channel.id
        shooty_context = context_manager.get_context(channel_id)
        # Keep a live channel reference so voice-channel presence can be resolved
        shooty_context.channel = reaction.message.channel

        logging.info(
            f"Reaction added: {reaction.emoji} by {user.name} in channel {channel_id}"
        )
        
        # Only handle reactions on the latest shooty message
        if reaction.message.id != shooty_context.current_st_message_id:
            logging.info("Ignoring reaction - not on latest shooty message")
            return
        
        # Handle thumbs up (solo queue)
        if str(reaction.emoji) == EMOJI["THUMBS_UP"]:
            shooty_context.add_soloq_user(user)
            logging.info(f"Added {user.name} to solo queue")
            
            # Track session participation
            await self._track_session_participation(shooty_context, user)

            await self._update_party_message(reaction.message, shooty_context)

            # Update bot status
            await self.bot.update_status_with_queue_count()
        
        # Handle 5️⃣ (fullstack only)
        elif str(reaction.emoji) == EMOJI["FULL_STACK"]:
            if not shooty_context.is_soloq_user(user):
                shooty_context.add_fullstack_user(user)
                logging.info(f"Added {user.name} to fullstack queue")
                
                # Track session participation
                await self._track_session_participation(shooty_context, user)

                await self._update_party_message(reaction.message, shooty_context)

                # Update bot status
                await self.bot.update_status_with_queue_count()
        
        # Handle ✅ (ready)
        elif str(reaction.emoji) == EMOJI["READY"]:
            shooty_context.bot_ready_user_set.add(user)
            logging.info(f"Marked {user.name} as ready")

            await self._update_party_message(reaction.message, shooty_context)
        
        # Handle 🔄 (refresh)
        elif str(reaction.emoji) == EMOJI["REFRESH"]:
            logging.info("Refresh emoji clicked")
            await self._refresh_status(reaction.message)
        
        # Handle 📣 (mention)
        elif str(reaction.emoji) == EMOJI["MENTION"]:
            logging.info("Mention emoji clicked")
            await self._mention_party(reaction.message)
    
    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]) -> None:
        """Handle when users remove reactions"""
        if user.bot or reaction.message.author != self.bot.user:
            return
        
        channel_id = reaction.message.channel.id
        shooty_context = context_manager.get_context(channel_id)
        # Keep a live channel reference so voice-channel presence can be resolved
        shooty_context.channel = reaction.message.channel

        logging.info(
            f"Reaction removed: {reaction.emoji} by {user.name} in channel {channel_id}"
        )
        
        # Only handle reactions on the latest shooty message
        if reaction.message.id != shooty_context.current_st_message_id:
            logging.info("Ignoring reaction removal - not on latest shooty message")
            return
        
        # Handle thumbs up removal (solo queue)
        if str(reaction.emoji) == EMOJI["THUMBS_UP"] and shooty_context.is_soloq_user(user):
            shooty_context.remove_soloq_user(user)
            # Also remove plus ones when user leaves party
            shooty_context.remove_plus_ones(user)
            logging.info(f"Removed {user.name} from solo queue and cleared their plus ones")

            await self._update_party_message(reaction.message, shooty_context)

            # Update bot status
            await self.bot.update_status_with_queue_count()

        # Handle 5️⃣ removal (fullstack)
        elif str(reaction.emoji) == EMOJI["FULL_STACK"] and user in shooty_context.bot_fullstack_user_set:
            shooty_context.remove_fullstack_user(user)
            # Also remove plus ones when user leaves party
            shooty_context.remove_plus_ones(user)
            logging.info(f"Removed {user.name} from fullstack queue and cleared their plus ones")

            await self._update_party_message(reaction.message, shooty_context)

            # Update bot status
            await self.bot.update_status_with_queue_count()
        
        # Handle ✅ removal (ready)
        elif str(reaction.emoji) == EMOJI["READY"] and user in shooty_context.bot_ready_user_set:
            shooty_context.bot_ready_user_set.remove(user)
            logging.info(f"Unmarked {user.name} as ready")

            await self._update_party_message(reaction.message, shooty_context)
    
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