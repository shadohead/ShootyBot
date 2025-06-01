import logging
from typing import Union
import discord
from discord.ext import commands
from context_manager import context_manager, to_names_list
from handlers.message_formatter import party_status_message
from data_manager import data_manager
from config import *

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
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]) -> None:
        """Handle when users add reactions"""
        if user.bot or reaction.message.author != self.bot.user:
            return
        
        channel_id = reaction.message.channel.id
        shooty_context = context_manager.get_context(channel_id)
        
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
            
            new_message = party_status_message(True, shooty_context)
            await reaction.message.edit(content=new_message)
            
            # Update bot status
            await self.bot.update_status_with_queue_count()
        
        # Handle 5️⃣ (fullstack only)
        elif str(reaction.emoji) == EMOJI["FULL_STACK"]:
            if not shooty_context.is_soloq_user(user):
                shooty_context.add_fullstack_user(user)
                logging.info(f"Added {user.name} to fullstack queue")
                
                # Track session participation
                await self._track_session_participation(shooty_context, user)
                
                new_message = party_status_message(True, shooty_context)
                await reaction.message.edit(content=new_message)
                
                # Update bot status
                await self.bot.update_status_with_queue_count()
        
        # Handle ✅ (ready)
        elif str(reaction.emoji) == EMOJI["READY"]:
            shooty_context.bot_ready_user_set.add(user)
            logging.info(f"Marked {user.name} as ready")
            
            new_message = party_status_message(True, shooty_context)
            await reaction.message.edit(content=new_message)
        
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
            logging.info(f"Removed {user.name} from solo queue")
            
            new_message = party_status_message(True, shooty_context)
            await reaction.message.edit(content=new_message)
            
            # Update bot status
            await self.bot.update_status_with_queue_count()
        
        # Handle 5️⃣ removal (fullstack)
        elif str(reaction.emoji) == EMOJI["FULL_STACK"] and user in shooty_context.bot_fullstack_user_set:
            shooty_context.remove_fullstack_user(user)
            logging.info(f"Removed {user.name} from fullstack queue")
            
            new_message = party_status_message(True, shooty_context)
            await reaction.message.edit(content=new_message)
            
            # Update bot status
            await self.bot.update_status_with_queue_count()
        
        # Handle ✅ removal (ready)
        elif str(reaction.emoji) == EMOJI["READY"] and user in shooty_context.bot_ready_user_set:
            shooty_context.bot_ready_user_set.remove(user)
            logging.info(f"Unmarked {user.name} as ready")
            
            new_message = party_status_message(True, shooty_context)
            await reaction.message.edit(content=new_message)
    
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